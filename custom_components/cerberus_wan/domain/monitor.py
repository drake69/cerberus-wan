"""The service that answers which provider is carrying the traffic."""

from __future__ import annotations

from dataclasses import dataclass

from .observation import Observation
from .ports import AddressProbe, AsnRegistry, Clock
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
    given a way to ask for an address, a way to ask who announces it, and a
    clock: what it does with the three is the subject of this class.
    """

    def __init__(
        self,
        probe: AddressProbe,
        registry: AsnRegistry,
        clock: Clock,
        settings: MonitorSettings,
    ) -> None:
        """Wire the monitor to its surroundings.

        Args:
            probe: how to ask for the public address.
            registry: how to ask which network announces an address.
            clock: how to ask what time it is.
            settings: the provider table and the labels to fall back on.
        """
        self._probe = probe
        self._registry = registry
        self._clock = clock
        self._settings = settings

    @property
    def settings(self) -> MonitorSettings:
        """Return the configuration this monitor is running with.

        Returns:
            The settings given at construction.
        """
        return self._settings

    async def observe(self) -> Observation:
        """Look at the network once and report what was seen.

        Returns:
            The reading: the address, the announcing network, and the label
            the two of them resolve to.
        """
        address = await self._probe.public_address()
        if address is None:
            return Observation(
                moment=self._clock.now(),
                address=None,
                asn=None,
                label=self._settings.disconnected_label,
            )

        asn = await self._registry.announcing_asn(address)
        return Observation(
            moment=self._clock.now(),
            address=address,
            asn=asn,
            label=self._settings.table.label_for(asn, self._settings.unknown_label),
        )
