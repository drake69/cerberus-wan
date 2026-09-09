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

from . import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DEFAULT_DISCONNECTED_LABEL,
    DEFAULT_UNKNOWN_LABEL,
    DOMAIN,
)
from .dns_lookup import resolve_announcing_asn, resolve_public_address
from .provider_table import resolve_label

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

# A share sensor holds 100 while its label is the active one and 0 otherwise.
# Recorded as a measurement, its long term mean over any window is therefore
# the percentage of time spent on that provider, which is the question the
# plain text sensor cannot answer.
ACTIVE = 100
INACTIVE = 0


class NetworkCoordinator(DataUpdateCoordinator):
    """Resolves the network once per cycle, for every entity of the entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Prepare the shared polling loop.

        Args:
            hass: the running Home Assistant instance.
            entry: the config entry holding the provider table and labels.
        """
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self._entry = entry

    def setting(self, key: str, default):
        """Read a setting, letting the options dialog override the setup value.

        Args:
            key: the configuration key to read.
            default: value returned when the key was never set.

        Returns:
            The effective value for this entry.
        """
        return self._entry.options.get(key, self._entry.data.get(key, default))

    async def _async_update_data(self) -> dict:
        """Resolve the address, the network, and the label they map to.

        Returns:
            A mapping with the public address, the autonomous system number
            and the label every entity of this entry should agree on.
        """
        address = await self.hass.async_add_executor_job(resolve_public_address)
        if address is None:
            return {
                "address": None,
                "asn": None,
                "label": self.setting(
                    CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
                ),
            }

        asn = await self.hass.async_add_executor_job(resolve_announcing_asn, address)
        label = resolve_label(
            self.setting(CONF_PROVIDERS, {}),
            asn,
            self.setting(CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL),
        )
        return {"address": address, "asn": asn, "label": label}


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
    coordinator = NetworkCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    labels = list(dict.fromkeys(coordinator.setting(CONF_PROVIDERS, {}).values()))
    labels.append(
        coordinator.setting(CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL)
    )
    labels.append(coordinator.setting(CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL))

    entities: list[SensorEntity] = [ProviderSensor(coordinator, entry)]
    entities += [ShareSensor(coordinator, entry, label) for label in labels]
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
        return self.coordinator.data["label"]

    @property
    def extra_state_attributes(self) -> dict:
        """Return the evidence behind the label.

        Returns:
            The public address and the announcing autonomous system number.
        """
        return {
            "public_address": self.coordinator.data["address"],
            "asn": self.coordinator.data["asn"],
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
        return ACTIVE if self.coordinator.data["label"] == self._label else INACTIVE
