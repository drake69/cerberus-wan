"""Tests for the options dialog, against a running Home Assistant.

The dialog that names a provider after the fact is the reason the history
exists, and the history only reaches it through the flow manager.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cerberus_wan import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DOMAIN,
)
from custom_components.cerberus_wan.config_flow import CONF_PROVIDER_TABLE
from custom_components.cerberus_wan.domain import Asn

DETECT = "custom_components.cerberus_wan.config_flow.detect_network"
SEEN = "custom_components.cerberus_wan.config_flow.seen_networks"


def make_entry(hass: HomeAssistant, providers: dict[str, str]) -> MockConfigEntry:
    """Register an entry holding a provider table, without starting it.

    Args:
        hass: the running Home Assistant instance.
        providers: the table the entry should hold.

    Returns:
        The entry, already known to Home Assistant.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cerberus WAN",
        data={
            CONF_PROVIDERS: providers,
            CONF_DISCONNECTED_LABEL: "Disconnected",
            CONF_UNKNOWN_LABEL: "Unknown",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def open_options(hass: HomeAssistant, entry, detected=None, seen=None):
    """Open the options dialog with the detection under control.

    Args:
        hass: the running Home Assistant instance.
        entry: the entry being reconfigured.
        detected: the address and network to pretend were detected.
        seen: the networks to pretend were seen before.

    Returns:
        The form result.
    """
    with (
        patch(DETECT, return_value=detected or (None, None)),
        patch(SEEN, return_value=seen or []),
    ):
        return await hass.config_entries.options.async_init(entry.entry_id)


def prefill(result) -> str:
    """Return the provider text the form opened with.

    Args:
        result: the form result to read.

    Returns:
        The default of the provider field.
    """
    for key in result["data_schema"].schema:
        if key == CONF_PROVIDER_TABLE:
            return key.default()
    raise AssertionError("the form has no provider field")


async def test_the_backup_is_offered_after_the_failover_ended(
    hass: HomeAssistant,
) -> None:
    """The whole point: naming it no longer has to happen while it is in use."""
    entry = make_entry(hass, {"35612": "Eolo"})
    result = await open_options(
        hass, entry, detected=("1.2.3.4", Asn(35612)), seen=[Asn(35612), Asn(51207)]
    )
    assert result["type"] is FlowResultType.FORM
    assert prefill(result).splitlines() == ["35612 = Eolo;", "51207 = ;"]


async def test_a_table_with_every_network_named_gains_no_row(
    hass: HomeAssistant,
) -> None:
    """Nothing left to name means nothing appended."""
    entry = make_entry(hass, {"35612": "Eolo", "51207": "Iliad"})
    result = await open_options(
        hass, entry, detected=("1.2.3.4", Asn(35612)), seen=[Asn(51207)]
    )
    assert prefill(result).splitlines() == ["35612 = Eolo;", "51207 = Iliad;"]


async def test_naming_the_backup_reaches_the_options(hass: HomeAssistant) -> None:
    """What the dialog saves is what the monitor will read on the reload."""
    entry = make_entry(hass, {"35612": "Eolo"})
    result = await open_options(
        hass, entry, detected=("1.2.3.4", Asn(35612)), seen=[Asn(51207)]
    )
    saved = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_PROVIDER_TABLE: "35612 = Eolo; 51207 = Iliad;"},
    )
    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert saved["data"][CONF_PROVIDERS] == {"35612": "Eolo", "51207": "Iliad"}
