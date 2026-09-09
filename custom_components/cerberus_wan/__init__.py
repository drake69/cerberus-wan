"""Cerberus WAN: tells which provider is currently carrying the traffic."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "cerberus_wan"
PLATFORMS = [Platform.SENSOR]

CONF_PROVIDERS = "providers"
CONF_DISCONNECTED_LABEL = "disconnected_label"
CONF_UNKNOWN_LABEL = "unknown_label"
CONF_CHANGE_TARGETS = "change_targets"

# Fired on every switchover, whether or not anything was hooked to it. It
# carries what changed, which a service call cannot, so an automation that
# needs to know where the traffic went triggers on this instead.
EVENT_PROVIDER_CHANGED = f"{DOMAIN}_provider_changed"

# Both defaults are plain English because the repository is English. They are
# user facing values, so whoever installs the integration overrides them in
# their own language from the configuration dialog.
DEFAULT_DISCONNECTED_LABEL = "Disconnected"
DEFAULT_UNKNOWN_LABEL = "Unknown"


def setting(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Read a setting, letting the options dialog override the setup value.

    Args:
        entry: the config entry to read from.
        key: the configuration key to read.
        default: value returned when the key was never set.

    Returns:
        The effective value for this entry.
    """
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry.

    Args:
        hass: the running Home Assistant instance.
        entry: the config entry being set up.

    Returns:
        True once the sensor platform has been forwarded.
    """
    entry.async_on_unload(entry.add_update_listener(_reload_on_options_change))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and its platforms.

    Args:
        hass: the running Home Assistant instance.
        entry: the config entry being removed.

    Returns:
        True when every platform unloaded cleanly.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload_on_options_change(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so an edited provider table applies immediately.

    Without this, a provider added from the options dialog would only take
    effect after a restart, which defeats the point of editing it there.

    Args:
        hass: the running Home Assistant instance.
        entry: the config entry whose options changed.
    """
    await hass.config_entries.async_reload(entry.entry_id)
