"""The sensors: which provider is carrying the traffic, and for how long."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import slugify

from . import DOMAIN
from .assembly import build_monitor
from .domain import Observation, WanMonitor

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

# A share sensor holds 100 while its label is the active one and 0 otherwise.
# Recorded as a measurement, its long term mean over any window is therefore
# the percentage of time spent on that provider, which is the question the
# plain text sensor cannot answer.
ACTIVE = 100
INACTIVE = 0


class NetworkCoordinator(DataUpdateCoordinator[Observation]):
    """Runs the monitor once per cycle, for every entity of the entry.

    The polling loop belongs to Home Assistant, the question being asked
    belongs to the monitor. This class is the seam between the two and holds
    no rule of its own.
    """

    def __init__(self, hass: HomeAssistant, monitor: WanMonitor) -> None:
        """Prepare the shared polling loop.

        Args:
            hass: the running Home Assistant instance.
            monitor: the domain service that answers the question.
        """
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._monitor = monitor

    @property
    def monitor(self) -> WanMonitor:
        """Return the monitor behind this loop.

        Returns:
            The monitor given at construction.
        """
        return self._monitor

    async def _async_update_data(self) -> Observation:
        """Ask the monitor what is carrying the traffic.

        Returns:
            The reading every entity of this entry should agree on.
        """
        return await self._monitor.observe()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the provider sensor and one share sensor per known label.

    Args:
        hass: the running Home Assistant instance.
        entry: the config entry holding the provider table.
        async_add_entities: callback used to register the entities.
    """
    monitor = build_monitor(hass, entry)
    coordinator = NetworkCoordinator(hass, monitor)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = [ProviderSensor(coordinator, entry)]
    entities += [
        ShareSensor(coordinator, entry, label) for label in monitor.settings.labels
    ]
    async_add_entities(entities)


class CerberusEntity(CoordinatorEntity[NetworkCoordinator], SensorEntity):
    """Common wiring: one device per entry, names derived from it."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NetworkCoordinator, entry: ConfigEntry) -> None:
        """Attach the entity to the shared coordinator and its device.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
        """
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "entry_type": "service",
        }

    @property
    def observation(self) -> Observation:
        """Return the reading every entity of this entry is showing.

        Returns:
            The latest observation.
        """
        return self.coordinator.data


class ProviderSensor(CerberusEntity):
    """Reports the provider label, or the disconnected or unknown label."""

    _attr_name = None
    _attr_icon = "mdi:dog"

    def __init__(self, coordinator: NetworkCoordinator, entry: ConfigEntry) -> None:
        """Name the entity after its entry.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
        """
        super().__init__(coordinator, entry)
        self._attr_unique_id = entry.entry_id

    @property
    def native_value(self) -> str:
        """Return the label of the network currently in use.

        Returns:
            The provider label, or the disconnected or unknown label.
        """
        return self.observation.label

    @property
    def extra_state_attributes(self) -> dict:
        """Return the evidence behind the label.

        Returns:
            The public address and the announcing autonomous system number.
        """
        asn = self.observation.asn
        return {
            "public_address": self.observation.address,
            "asn": asn.number if asn else None,
        }


class ShareSensor(CerberusEntity):
    """Holds 100 while its label is active, so its mean is a percentage."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-donut"

    def __init__(
        self, coordinator: NetworkCoordinator, entry: ConfigEntry, label: str
    ) -> None:
        """Bind the entity to the one label it tracks.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
            label: the label whose share of time this entity measures.
        """
        super().__init__(coordinator, entry)
        self._label = label
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_share_{slugify(label)}"

    @property
    def native_value(self) -> int:
        """Return 100 while this label is the active one, 0 otherwise.

        Returns:
            The instantaneous share, whose long term mean is the percentage of
            time spent on this provider.
        """
        return ACTIVE if self.observation.label == self._label else INACTIVE
