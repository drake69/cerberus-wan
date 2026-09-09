"""Composition root: where a config entry becomes a working monitor.

This is the only module that knows both halves. The domain is built here, the
adapters are chosen here, and the wiring between them happens here, so that
neither the entities nor the dialogs have to know what a DNS resolver is.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DEFAULT_DISCONNECTED_LABEL,
    DEFAULT_UNKNOWN_LABEL,
    DOMAIN,
)
from .domain import Asn, MonitorSettings, ProviderTable, WanMonitor
from .infrastructure.clock import SystemClock
from .infrastructure.dns import CymruAsnRegistry, DnsAddressProbe
from .infrastructure.store import DelayedCacheStore

# Shorter than the timeout the sensors run with: the detection happens while
# the dialog is opening, and a slow lookup would look like a frozen form.
# Failing to detect is harmless, the form simply opens without a suggestion.
DETECTION_TIMEOUT = 2.0

# One table for the installation and not one per entry: who announces an
# address is a fact about the address, not about whoever is watching it.
STORAGE_KEY = f"{DOMAIN}.asn_cache"
STORAGE_VERSION = 1


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


def monitor_settings(entry: ConfigEntry) -> MonitorSettings:
    """Translate a config entry into what the domain understands.

    Args:
        entry: the config entry holding the provider table and the labels.

    Returns:
        The settings the monitor runs with.
    """
    return MonitorSettings(
        table=ProviderTable.from_mapping(setting(entry, CONF_PROVIDERS, {})),
        disconnected_label=setting(
            entry, CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
        ),
        unknown_label=setting(entry, CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL),
    )


def build_monitor(hass: HomeAssistant, entry: ConfigEntry) -> WanMonitor:
    """Assemble the monitor this entry needs.

    Args:
        hass: the running Home Assistant instance.
        entry: the config entry being set up.

    Returns:
        A monitor wired to DNS and to the machine clock.
    """
    return WanMonitor(
        probe=DnsAddressProbe(hass.async_add_executor_job),
        registry=CymruAsnRegistry(hass.async_add_executor_job),
        clock=SystemClock(),
        settings=monitor_settings(entry),
        store=DelayedCacheStore(Store(hass, STORAGE_VERSION, STORAGE_KEY)),
    )


async def detect_network(hass: HomeAssistant) -> tuple[str | None, Asn | None]:
    """Resolve address and network quickly, to prefill a dialog.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The public address and the announcing network, either of which is None
        when it could not be determined in time.
    """
    probe = DnsAddressProbe(hass.async_add_executor_job, DETECTION_TIMEOUT)
    address = await probe.public_address()
    if address is None:
        return None, None
    registry = CymruAsnRegistry(hass.async_add_executor_job, DETECTION_TIMEOUT)
    return address, await registry.announcing_asn(address)
