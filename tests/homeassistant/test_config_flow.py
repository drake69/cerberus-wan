"""Tests for the dialogs, against a running Home Assistant.

These are the tests the domain suite cannot write: what reaches the config
entry depends on the form, on the selector the form is built with, and on the
flow manager that carries the values between them.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.cerberus_wan import CONF_PROVIDERS, DOMAIN
from custom_components.cerberus_wan.config_flow import CONF_PROVIDER_TABLE
from custom_components.cerberus_wan.domain import Asn

DETECT = "custom_components.cerberus_wan.config_flow.detect_network"
SEEN = "custom_components.cerberus_wan.config_flow.seen_networks"


async def open_form(hass: HomeAssistant, detected=None, seen=None):
    """Open the setup dialog with the network detection under control.

    Args:
        hass: the running Home Assistant instance.
        detected: the address and network to pretend were detected.
        seen: the networks to pretend were seen before.

    Returns:
        The form result.
    """
    with (
        patch(DETECT, return_value=detected or (None, None)),
        patch(SEEN, return_value=seen or []),
    ):
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )


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


async def test_the_form_offers_the_detected_network(hass: HomeAssistant) -> None:
    """The network in use arrives in the field, closed and without a name."""
    result = await open_form(hass, detected=("1.2.3.4", Asn(35612)))
    assert result["type"] is FlowResultType.FORM
    assert prefill(result) == "35612 = ;"


async def test_the_form_offers_the_networks_seen_before(hass: HomeAssistant) -> None:
    """A network seen during an earlier failover is still nameable."""
    result = await open_form(
        hass, detected=("1.2.3.4", Asn(35612)), seen=[Asn(35612), Asn(51207)]
    )
    assert prefill(result).splitlines() == ["35612 = ;", "51207 = ;"]


async def test_a_failed_detection_still_opens_the_form(hass: HomeAssistant) -> None:
    """Losing the lookup must not cost the dialog."""
    result = await open_form(hass)
    assert result["type"] is FlowResultType.FORM
    assert prefill(result) == ""


async def test_two_providers_on_one_line_reach_the_entry_apart(
    hass: HomeAssistant,
) -> None:
    """The regression: the field can hand the table back on a single line."""
    result = await open_form(hass, detected=("1.2.3.4", Asn(35612)))
    created = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PROVIDER_TABLE: "35612 = Eolo; 51207 = Iliad;"},
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_PROVIDERS] == {"35612": "Eolo", "51207": "Iliad"}


async def test_a_typo_does_not_keep_the_dialog_open(hass: HomeAssistant) -> None:
    """An unreadable row costs one provider, never a form that will not close."""
    result = await open_form(hass, detected=("1.2.3.4", Asn(35612)))
    created = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PROVIDER_TABLE: "35612 = Eolo; nonsense; 51207 = ;"},
    )
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_PROVIDERS] == {"35612": "Eolo"}
