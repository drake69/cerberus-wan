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
from .domain import ChangeWindow, LabelTimeline, Observation, WanMonitor

_LOGGER = logging.getLogger(__name__)

# The address is asked for every fifteen seconds because that is the question
# that detects a switchover, and a switchover noticed a minute late is a
# switchover noticed too late. It costs one DNS query: who owns the address is
# answered from the local table, and asked again only when the address changes.
SCAN_INTERVAL = timedelta(seconds=15)

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

    @property
    def monitor(self) -> WanMonitor:
        """Return the monitor behind the shared loop.

        Returns:
            The monitor every entity of this entry is reading.
        """
        return self.coordinator.monitor


@dataclass
class StoredTimeline(ExtraStoredData):
    """The timeline as it survives a restart."""

    segments: list[list[str]]

    def as_dict(self) -> dict:
        """Return what goes into the restore store.

        Returns:
            The segments, each a moment and the label it opened.
        """
        return {"segments": self.segments}


class ProviderSensor(CerberusEntity, RestoreEntity):
    """Reports the provider label, or the disconnected or unknown label.

    It is also the entity that persists the timeline the shares are computed
    from. That job belongs to an entity that exists whatever the configuration
    says, and the shares themselves do not qualify: renaming a provider
    removes its entity and would take the record of the whole day with it.
    """

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
        """Return the evidence behind the label, and the reach of the shares.

        Returns:
            The public address, the announcing autonomous system number, and
            how many hours of record the share sensors are speaking for. The
            last one belongs here rather than on each share: it is a fact
            about the installation, and this entity is the one that writes on
            every cycle anyway.
        """
        asn = self.observation.asn
        return {
            "public_address": self.observation.address,
            "asn": asn.number if asn else None,
            "covered_hours": self.monitor.covered_hours,
        }

    @property
    def extra_restore_state_data(self) -> StoredTimeline:
        """Return the timeline to keep across a restart.

        Returns:
            The segments currently held.
        """
        return StoredTimeline(self.monitor.timeline.to_list())

    async def async_added_to_hass(self) -> None:
        """Take back the timeline the shares were computed from.

        Without this a restart would empty the day and every provider would
        read as a share of the minutes since the restart. The segment that was
        open when Home Assistant went down is credited to the label it had:
        the line is not known to have moved while nobody was watching, and
        assuming it did would be a guess in the other direction.
        """
        await super().async_added_to_hass()
        stored = await self.async_get_last_extra_data()
        if stored is None:
            return
        self.monitor.timeline.adopt(
            LabelTimeline.from_list(stored.as_dict().get("segments"))
        )
        self.monitor.expire_changes()
        # The shares are read by other entities, which may already have
        # published a percentage of the seconds since the restart. Telling the
        # loop is what republishes them now instead of on the next cycle.
        self.coordinator.async_update_listeners()


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
    def publication(self) -> object:
        """Return what has to move before this entity writes its state.

        The state itself, for an entity whose attributes say nothing a reader
        would act upon. An entity whose attributes do carry something acted
        upon overrides this, so a change there is published rather than kept
        waiting for the number to move.

        Returns:
            The value compared against what was last written.
        """
        return self.native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write the state only when what is reported has changed."""
        value = self.publication
        if value == self._published:
            return
        self._published = value
        super()._handle_coordinator_update()


class ShareSensor(StatisticEntity):
    """How much of the recorded day this provider carried the traffic.

    The number is a share of what is on the record, not of the wall clock: an
    installation running for two hours can only speak for those two hours, and
    the hours it can speak for are published on the provider sensor rather than
    folded into this percentage.
    """

    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:chart-donut"
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: NetworkCoordinator, entry: ConfigEntry, label: str
    ) -> None:
        """Bind the entity to the one label it measures.

        Args:
            coordinator: the shared polling loop.
            entry: the config entry this entity belongs to.
            label: the label whose share of the day this entity measures.
        """
        super().__init__(coordinator, entry)
        self._label = label
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_share_{slugify(label)}"

    @property
    def active(self) -> bool:
        """Report whether this provider is the one carrying right now.

        Returns:
            True while this label is the one being reported.
        """
        return self.observation.label == self._label

    @property
    def native_value(self) -> float:
        """Return the percentage of the recorded day spent on this provider.

        Returns:
            The share, zero before anything has been recorded.
        """
        return self.monitor.share_of(self._label)

    @property
    def publication(self) -> object:
        """Return the number and whether this provider is carrying.

        A switchover can move the flag without moving the percentage, because
        a percentage rounded to a tenth does not notice a second. Publishing on
        the pair is what keeps the flag from going stale until the number
        happens to move.

        Returns:
            The pair compared against what was last written.
        """
        return (self.native_value, self.active)

    @property
    def extra_state_attributes(self) -> dict:
        """Return what the percentage alone does not say.

        Returns:
            Whether this provider is the one carrying right now.
        """
        return {"active": self.active}


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
