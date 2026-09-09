"""The service that answers which provider is carrying the traffic."""

from __future__ import annotations

from dataclasses import dataclass

from .asn import Asn
from .asn_cache import AsnCache
from .change_window import ChangeWindow
from .observation import Observation
from .ports import AddressProbe, AsnRegistry, CacheStore, Clock
from .provider_table import ProviderTable


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
    ) -> None:
        """Wire the monitor to its surroundings.

        Args:
            probe: how to ask for the public address.
            registry: how to ask which network announces an address.
            clock: how to ask what time it is.
            settings: the provider table and the labels to fall back on.
            store: where the table of known addresses survives a restart, or
                None to keep it in memory for the life of the process.
        """
        self._probe = probe
        self._registry = registry
        self._clock = clock
        self._settings = settings
        self._store = store
        self._cache = AsnCache()
        self._window = ChangeWindow()
        self._current: Observation | None = None

    @property
    def current(self) -> Observation | None:
        """Return the last reading taken.

        Returns:
            The reading, or None before the first observation.
        """
        return self._current

    @property
    def window(self) -> ChangeWindow:
        """Return the moving window of switchovers.

        Returns:
            The window this monitor has been filling.
        """
        return self._window

    @property
    def changes_last_day(self) -> int:
        """Return how many times the provider changed in the last day.

        Returns:
            The number of changes inside the window.
        """
        return self._window.count(self._clock.now())

    @property
    def changes_per_hour(self) -> float:
        """Return the moving average of changes per hour over the window.

        Returns:
            The changes per hour.
        """
        return self._window.per_hour(self._clock.now())

    def expire_changes(self) -> bool:
        """Drop the changes that have left the window.

        Returns:
            True when something was dropped, so the caller knows the published
            statistics are now out of date.
        """
        return self._window.expire(self._clock.now())

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

        A reading that differs from the one before it is a switchover, and
        is noted in the window on the way out.

        Returns:
            The reading: the address, the announcing network, and the label
            the two of them resolve to.
        """
        address = await self._probe.public_address()
        if address is None:
            return self._record(
                Observation(
                    moment=self._clock.now(),
                    address=None,
                    asn=None,
                    label=self._settings.disconnected_label,
                )
            )

        asn = await self._asn_for(address)
        return self._record(
            Observation(
                moment=self._clock.now(),
                address=address,
                asn=asn,
                label=self._settings.table.label_for(
                    asn, self._settings.unknown_label
                ),
            )
        )

    def _record(self, observation: Observation) -> Observation:
        """Keep the reading, and note it in the window when it is a change.

        Args:
            observation: the reading just taken.

        Returns:
            The same reading, so the caller can return it.
        """
        if observation.follows(self._current):
            self._window.record(observation.moment)
        self._current = observation
        return observation

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
