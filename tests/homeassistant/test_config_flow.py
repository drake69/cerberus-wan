"""Tests for the dialogs, against a running Home Assistant.

These are the tests the domain suite cannot write: what reaches the config
entry depends on the form, on the selector the form is built with, and on the
flow manager that carries the values between them.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
import voluptuous_serialize
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv

from custom_components.cerberus_wan import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DOMAIN,
)
from custom_components.cerberus_wan.config_flow import (
    CONF_PROVIDER_TABLE,
    MAX_LABEL_LENGTH,
    build_schema,
)
from custom_components.cerberus_wan.domain import Asn

DETECT = "custom_components.cerberus_wan.config_flow.detect_network"
SEEN = "custom_components.cerberus_wan.config_flow.seen_networks"
PROBE = "custom_components.cerberus_wan.assembly.DnsAddressProbe"
REGISTRY = "custom_components.cerberus_wan.assembly.CymruAsnRegistry"


class Silent:
    """A network that answers nothing, standing in for both lookups."""

    async def public_address(self) -> None:
        """Report no address.

        Returns:
            None, always.
        """
        return

    async def announcing_asn(self, address: str) -> None:
        """Report no announcing network.

        Args:
            address: the address being resolved, ignored here.

        Returns:
            None, always.
        """
        return


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


async def submit(hass: HomeAssistant, flow_id: str, table: str):
    """Fill the provider field and close the dialog, with the network silenced.

    Closing the dialog creates the entry, and creating the entry sets the
    component up, which would otherwise send the real lookups out. Without
    this the test passes or fails depending on whether the first refresh gets
    a slice of the loop before the test ends.

    Args:
        hass: the running Home Assistant instance.
        flow_id: the dialog to submit.
        table: the provider text to submit.

    Returns:
        The result of closing the dialog.
    """
    with (
        patch(PROBE, return_value=Silent()),
        patch(REGISTRY, return_value=Silent()),
    ):
        created = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_PROVIDER_TABLE: table}
        )
        await hass.async_block_till_done()
    return created


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
    created = await submit(hass, result["flow_id"], "35612 = Eolo; 51207 = Iliad;")
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_PROVIDERS] == {"35612": "Eolo", "51207": "Iliad"}


async def test_a_typo_does_not_keep_the_dialog_open(hass: HomeAssistant) -> None:
    """An unreadable row costs one provider, never a form that will not close."""
    result = await open_form(hass, detected=("1.2.3.4", Asn(35612)))
    created = await submit(hass, result["flow_id"], "35612 = Eolo; nonsense; 51207 = ;")
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert created["data"][CONF_PROVIDERS] == {"35612": "Eolo"}


def test_a_label_that_would_not_fit_a_state_is_refused() -> None:
    """A label longer than the cap never reaches the entry.

    Home Assistant refuses a state over 255 characters, and a sensor whose
    state is refused does not report an error the person can see: it just
    stops updating. Failing on the form is the visible version of the same
    rule.
    """
    schema = build_schema({})
    with pytest.raises(vol.Invalid):
        schema({CONF_DISCONNECTED_LABEL: "x" * (MAX_LABEL_LENGTH + 1)})


def test_a_label_at_the_cap_still_passes() -> None:
    """The boundary belongs to the person typing, not to the validator."""
    schema = build_schema({})
    validated = schema({CONF_UNKNOWN_LABEL: "x" * MAX_LABEL_LENGTH})
    assert validated[CONF_UNKNOWN_LABEL] == "x" * MAX_LABEL_LENGTH


def test_the_form_can_still_be_rendered() -> None:
    """The frontend builds the dialog from a serialised schema.

    A validator the serialiser cannot express would not fail a test that only
    calls the schema in Python: it would fail as a dialog that does not open.
    """
    fields = voluptuous_serialize.convert(
        build_schema({}), custom_serializer=cv.custom_serializer
    )
    labels = {f["name"]: f for f in fields}
    assert labels[CONF_DISCONNECTED_LABEL]["lengthMax"] == MAX_LABEL_LENGTH
    assert labels[CONF_UNKNOWN_LABEL]["lengthMax"] == MAX_LABEL_LENGTH
