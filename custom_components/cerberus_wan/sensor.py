"""The sensors: which provider is carrying the traffic, and for how long."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import slugify

from . import DOMAIN
from .assembly import build_monitor
from .domain import ChangeWindow, Observation, WanMonitor

_LOGGER = logging.getLogger(__name__)

# The address is asked for every fifteen seconds because that is the question
# that detects a switchover, and a switchover noticed a minute late is a
# switchover noticed too late. It costs one DNS query: who owns the address is
# answered from the local table, and asked again only when the address changes.
SCAN_INTERVAL = timedelta(seconds=15)

# A share sensor holds 100 while its label is the active one and 0 otherwise.
# Recorded as a measurement, its long term mean over any window is therefore
# the percentage of time spent on that provider, which is the question the
# plain text sensor cannot answer.
ACTIVE = 100
INACTIVE = 0

# The window has to be swept often enough for a change to leave it on time,
# and no more often than that: sweeping it hourly is what makes the statistics
# a rolling day rather than a total that only ever grows.
STATISTICS_INTERVAL = timedelta(hours=1)


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

    @callback
    def async_expire_statistics(self, now=None) -> None:
        """Let the oldest changes leave the window, and republish if they did.

        Args:
            now: the moment the timer fired, which the monitor does not need
                because it carries its own clock.
        """
        if self._monitor.expire_changes():
            self.async_update_listeners()


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
    await monitor.prime()
    coordinator = NetworkCoordinator(hass, monitor)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = [
        ProviderSensor(coordinator, entry),
        ChangeCountSensor(coordinator, entry),
        ChangeRateSensor(coordinator, entry),
    ]
    entities += [
        ShareSensor(coordinator, entry, label) for label in monitor.settings.labels
    ]
    async_add_entities(entities)

    entry.async_on_unload(
        async_track_time_interval(
            hass, coordinator.async_expire_statistics, STATISTICS_INTERVAL
        )
    )


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


class StatisticEntity(CerberusEntity):
    """A number about the changes, published only when it actually moves.

    The polling loop runs every fifteen seconds, and the count of the last day
    is the same number on almost all of them. Writing it anyway would be five
    thousand state writes a day that say nothing.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NetworkCoordinator, entry: ConfigEntry) -> None:
        """Remember nothing has been published yet.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
        """
        super().__init__(coordinator, entry)
        self._published = None

    @property
    def monitor(self) -> WanMonitor:
        """Return the monitor holding the window.

        Returns:
            The monitor behind the coordinator.
        """
        return self.coordinator.monitor

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write the state only when the number reported has changed."""
        value = self.native_value
        if value == self._published:
            return
        self._published = value
        super()._handle_coordinator_update()


@dataclass
class StoredWindow(ExtraStoredData):
    """The window as it survives a restart."""

    moments: list[str]

    def as_dict(self) -> dict:
        """Return what goes into the restore store.

        Returns:
            The moments, as ISO 8601 strings.
        """
        return {"moments": self.moments}


class ChangeCountSensor(StatisticEntity, RestoreEntity):
    """How many times the provider changed in the last twenty four hours."""

    _attr_name = "Changes in 24 hours"
    _attr_native_unit_of_measurement = "changes"
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, coordinator: NetworkCoordinator, entry: ConfigEntry) -> None:
        """Name the entity after what it counts.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
        """
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_changes_24h"

    @property
    def native_value(self) -> int:
        """Return the number of changes inside the window.

        Returns:
            The count over the last twenty four hours.
        """
        return self.monitor.changes_last_day

    @property
    def extra_state_attributes(self) -> dict:
        """Return what the count alone does not say.

        Returns:
            When the provider last changed, and how wide the window is.
        """
        window = self.monitor.window
        last = window.last
        return {
            "last_change": last.isoformat() if last else None,
            "window_hours": round(window.window.total_seconds() / 3600),
        }

    @property
    def extra_restore_state_data(self) -> StoredWindow:
        """Return the window to keep across a restart.

        Returns:
            The moments currently held.
        """
        return StoredWindow(self.monitor.window.to_list())

    async def async_added_to_hass(self) -> None:
        """Take back the window this entity was holding before the restart.

        Without this a restart would empty the last twenty four hours, and a
        statistic that resets whenever Home Assistant does is a statistic that
        lies. This entity is the one that persists the window; the rate sensor
        reads the same one.
        """
        await super().async_added_to_hass()
        stored = await self.async_get_last_extra_data()
        if stored is None:
            return
        self.monitor.window.adopt(
            ChangeWindow.from_list(stored.as_dict().get("moments"))
        )
        self.monitor.expire_changes()
        self.async_write_ha_state()


class ChangeRateSensor(StatisticEntity):
    """The moving average of changes per hour over the same window."""

    _attr_name = "Changes per hour"
    _attr_native_unit_of_measurement = "changes/h"
    _attr_icon = "mdi:chart-line-variant"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: NetworkCoordinator, entry: ConfigEntry) -> None:
        """Name the entity after what it averages.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
        """
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_changes_per_hour"

    @property
    def native_value(self) -> float:
        """Return the average number of changes per hour.

        Returns:
            The count over the window, divided by the width of the window.
        """
        return self.monitor.changes_per_hour
