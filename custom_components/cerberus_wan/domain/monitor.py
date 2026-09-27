"""The service that answers which provider is carrying the traffic."""

from __future__ import annotations

from dataclasses import dataclass

from .asn import Asn
from .asn_cache import AsnCache
from .change_window import ChangeWindow
from .label_timeline import LabelTimeline
from .observation import Observation
from .ports import AddressProbe, AsnRegistry, CacheStore, ChangeListener, Clock
from .provider_table import ProviderTable
from .transition import classify


@dataclass(frozen=True)
class MonitorSettings:
    """Everything the monitor needs from whoever configured it."""

    table: ProviderTable
    disconnected_label: str
    unknown_label: str

    @property
    def labels(self) -> list[str]:
        """Return every label this configuration can ever produce.

        Whoever builds one entity per label needs this list, and it is the
        configuration that knows it, not the entity.

        Returns:
            The labels, without repeats, in a stable order.
        """
        return list(
            dict.fromkeys(
                [*self.table.known_labels, self.disconnected_label, self.unknown_label]
            )
        )


class WanMonitor:
    """Looks at the network and says which provider is carrying the traffic.

    Knows nothing about Home Assistant, about DNS, or about sensors. It is
    given a way to ask for an address, a way to ask who announces it, a clock
    and somewhere to keep what it learns: what it does with them is the
    subject of this class.
    """

    def __init__(
        self,
        probe: AddressProbe,
        registry: AsnRegistry,
        clock: Clock,
        settings: MonitorSettings,
        store: CacheStore | None = None,
        listener: ChangeListener | None = None,
    ) -> None:
        """Wire the monitor to its surroundings.

        Args:
            probe: how to ask for the public address.
            registry: how to ask which network announces an address.
            clock: how to ask what time it is.
            settings: the provider table and the labels to fall back on.
            store: where the table of known addresses survives a restart, or
                None to keep it in memory for the life of the process.
            listener: who to tell when the provider changes, if anybody.
        """
        self._probe = probe
        self._registry = registry
        self._clock = clock
        self._settings = settings
        self._store = store
        self._listener = listener
        self._cache = AsnCache()
        self._window = ChangeWindow()
        self._outages = ChangeWindow()
        self._timeline = LabelTimeline()
        self._current: Observation | None = None
        self._last_resolved: Observation | None = None

    @property
    def current(self) -> Observation | None:
        """Return the last reading taken.

        Returns:
            The reading, or None before the first observation.
        """
        return self._current

    @property
    def window(self) -> ChangeWindow:
        """Return the moving window of provider changes.

        Returns:
            The window this monitor has been filling.
        """
        return self._window

    @property
    def outages(self) -> ChangeWindow:
        """Return the moving window of line interruptions.

        Kept apart from the window of provider changes because the two answer
        different questions: how often the traffic changed hands, and how often
        the line went down. Folding them together is what made a router
        renegotiating its session look like two failovers.

        Returns:
            The window this monitor has been filling.
        """
        return self._outages

    @property
    def timeline(self) -> LabelTimeline:
        """Return the record of which provider carried the traffic and when.

        Returns:
            The timeline this monitor has been filling.
        """
        return self._timeline

    def share_of(self, label: str) -> float:
        """Return the percentage of the recorded day spent on a provider.

        Args:
            label: the provider to report on.

        Returns:
            The percentage, zero before anything has been recorded.
        """
        return self._timeline.share(label, self._clock.now())

    @property
    def covered_hours(self) -> float:
        """Return how much of the window the shares can speak for.

        A share of two hours of record is not a share of the day, and whoever
        reads the number is entitled to know which one it is.

        Returns:
            The hours on the record, at most the width of the window.
        """
        return round(self._timeline.covered(self._clock.now()) / 3600, 2)

    @property
    def changes_last_day(self) -> int:
        """Return how many times the provider changed in the last day.

        Returns:
            The number of provider changes inside the window.
        """
        return self._window.count(self._clock.now())

    @property
    def outages_last_day(self) -> int:
        """Return how many times the line went down in the last day.

        Only the moment the connection was lost is counted. The return of the
        line is the other end of the same interruption, and counting it as well
        would report every outage twice.

        Returns:
            The number of interruptions inside the window.
        """
        return self._outages.count(self._clock.now())

    @property
    def changes_per_hour(self) -> float:
        """Return the moving average of changes per hour over the window.

        Returns:
            The changes per hour.
        """
        return self._window.per_hour(self._clock.now())

    def expire_changes(self) -> bool:
        """Drop the changes, the interruptions and the segments that aged out.

        All three records are swept in one call because all three are read by
        entities of the same entry: sweeping one and not the others would
        publish a count of the last day next to a share of something longer.

        Returns:
            True when something was dropped, so the caller knows the published
            statistics are now out of date.
        """
        now = self._clock.now()
        dropped_changes = self._window.expire(now)
        dropped_outages = self._outages.expire(now)
        dropped_segments = self._timeline.expire(now)
        return dropped_changes or dropped_outages or dropped_segments

    @property
    def cache(self) -> AsnCache:
        """Return the table of addresses already resolved.

        Returns:
            The cache this monitor is answering from.
        """
        return self._cache

    async def prime(self) -> None:
        """Load what previous runs learned about addresses.

        Called once before the first observation. Addresses nobody has seen
        for a long time are dropped on the way in, so the table does not grow
        for the life of the installation.
        """
        if self._store is None:
            return
        self._cache = AsnCache.from_dict(await self._store.load())
        self._cache.forget_old(self._clock.now())

    @property
    def settings(self) -> MonitorSettings:
        """Return the configuration this monitor is running with.

        Returns:
            The settings given at construction.
        """
        return self._settings

    async def observe(self) -> Observation:
        """Look at the network once and report what was seen.

        A reading whose label differs from the one before it is a movement: it
        is classified, counted if it is worth counting, and whoever asked to be
        told is told what kind of movement it was.

        Returns:
            The reading: the address, the announcing network, and the label
            the two of them resolve to.
        """
        return await self._settle(await self._read())

    async def _read(self) -> Observation:
        """Resolve the network as it is right now.

        Returns:
            The reading, with no side effect on the record.
        """
        address = await self._probe.public_address()
        if address is None:
            return Observation(
                moment=self._clock.now(),
                address=None,
                asn=None,
                label=self._settings.disconnected_label,
            )

        asn = await self._asn_for(address)
        if asn is None:
            return Observation(
                moment=self._clock.now(),
                address=address,
                asn=None,
                label=self._held_label(),
            )

        return Observation(
            moment=self._clock.now(),
            address=address,
            asn=asn,
            label=self._settings.table.label_for(asn, self._settings.unknown_label),
        )

    def _held_label(self) -> str:
        """Return what to report while it cannot be said who is carrying.

        The traffic is getting out, so something is carrying it: what cannot be
        said right now is what. Reporting the unknown label here would announce
        a change of provider that nobody made, and it happens exactly when a
        line has just come back on a new address, which is the moment an
        automation hooked to a switchover must not fire. The last answer is the
        likeliest one, so it is held until the lookup succeeds, which the short
        retry of the address table keeps to a couple of minutes. An
        installation that has never resolved anything has nothing to hold and
        says so.

        Returns:
            The label of the last reading whose network was known, or the
            unknown label when there has never been one.
        """
        if self._last_resolved is None:
            return self._settings.unknown_label
        return self._last_resolved.label

    async def _settle(self, observation: Observation) -> Observation:
        """Keep the reading, and act on it when it is a change.

        Args:
            observation: the reading just taken.

        Returns:
            The same reading, so the caller can return it.
        """
        previous = self._current
        self._current = observation
        self._timeline.record(observation.moment, observation.label)
        if not observation.follows(previous):
            self._remember_resolved(observation)
            return observation

        transition = classify(previous, observation, self._last_resolved)
        self._remember_resolved(observation)

        if transition.is_provider_change:
            self._window.record(observation.moment)
        if transition.is_outage:
            self._outages.record(observation.moment)
        if self._listener is not None:
            await self._listener.changed(transition)
        return observation

    def _remember_resolved(self, observation: Observation) -> None:
        """Keep the reading as the baseline, when it has a network to be one.

        The baseline has to survive the readings that carry no network,
        otherwise a failover that happens while the line is down has nothing to
        be compared against and reads as a line coming back.

        Args:
            observation: the reading just taken.
        """
        if observation.resolved:
            self._last_resolved = observation

    async def _asn_for(self, address: str) -> Asn | None:
        """Return who announces an address, asking only when it is not known.

        This is the reason the table exists. The public address has to be
        asked for on every cycle, because that is the question that detects a
        switchover. Who owns that address does not have to be: the answer is
        the same tomorrow as today, so it is asked once and kept.

        Args:
            address: the address to resolve.

        Returns:
            The announcing network, or None when it could not be determined.
        """
        now = self._clock.now()
        known = self._cache.fresh(address, now)
        if known is not None:
            return known.asn

        asn = await self._registry.announcing_asn(address)
        self._cache.remember(address, asn, now)
        if self._store is not None:
            await self._store.save(self._cache.to_dict())
        return asn
