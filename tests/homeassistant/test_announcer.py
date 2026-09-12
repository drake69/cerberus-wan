"""Tests for what a switchover sets in motion.

This is the only place in the integration that makes Home Assistant do
something on behalf of whoever configured it. Everything else reports; this
starts automations and scripts. It is worth checking that it starts exactly
what it was told to start, and nothing next to it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.cerberus_wan import (
    CONF_CHANGE_TARGETS,
    DOMAIN,
    EVENT_PROVIDER_CHANGED,
)
from custom_components.cerberus_wan.announcer import HassAnnouncer
from custom_components.cerberus_wan.domain import Asn, Observation

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

EOLO = Observation(moment=MOMENT, address="1.2.3.4", asn=Asn(35612), label="Eolo")
ILIAD = Observation(moment=MOMENT, address="5.6.7.8", asn=Asn(51207), label="Iliad")
DOWN = Observation(moment=MOMENT, address=None, asn=None, label="Disconnected")


def announcer_over(hass: HomeAssistant, targets: list[str]) -> HassAnnouncer:
    """Build an announcer bound to an entry hooked to the given targets.

    Args:
        hass: the running Home Assistant instance.
        targets: what the entry says to start on a change.

    Returns:
        The announcer under test.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANGE_TARGETS: targets})
    entry.add_to_hass(hass)
    return HassAnnouncer(hass, entry)


@pytest.fixture(name="fired")
def fired_events(hass: HomeAssistant) -> list:
    """Collect the switchover events fired during a test.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The list the listener appends to, filled as the test runs.
    """
    events: list = []
    hass.bus.async_listen(EVENT_PROVIDER_CHANGED, events.append)
    return events


async def test_the_event_carries_what_changed(hass: HomeAssistant, fired: list) -> None:
    """Whoever writes their own trigger reads the change off the event."""
    await announcer_over(hass, []).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert len(fired) == 1
    assert fired[0].data["previous_label"] == "Eolo"
    assert fired[0].data["label"] == "Iliad"
    assert fired[0].data["public_address"] == "5.6.7.8"
    assert fired[0].data["asn"] == 51207
    assert fired[0].data["changed_at"] == MOMENT.isoformat()


async def test_the_event_says_which_entry_it_came_from(
    hass: HomeAssistant, fired: list
) -> None:
    """Two lines watched by two entries must be tellable apart."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CHANGE_TARGETS: []})
    entry.add_to_hass(hass)
    await HassAnnouncer(hass, entry).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert fired[0].data["entry_id"] == entry.entry_id


async def test_going_down_is_announced_with_no_network(
    hass: HomeAssistant, fired: list
) -> None:
    """Losing the line is a change like any other, with nothing to resolve."""
    await announcer_over(hass, []).provider_changed(EOLO, DOWN)
    await hass.async_block_till_done()

    assert fired[0].data["label"] == "Disconnected"
    assert fired[0].data["asn"] is None
    assert fired[0].data["public_address"] is None


async def test_the_event_is_fired_even_with_nothing_hooked(
    hass: HomeAssistant, fired: list
) -> None:
    """Hooking nothing is a choice, not a reason to stay silent."""
    await announcer_over(hass, []).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert len(fired) == 1


async def test_an_automation_keeps_its_own_conditions(hass: HomeAssistant) -> None:
    """An automation that says "only at night" means it, started or not."""
    calls = async_mock_service(hass, "automation", "trigger")
    await announcer_over(hass, ["automation.call_me"]).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == ["automation.call_me"]
    assert calls[0].data["skip_condition"] is False


async def test_a_script_receives_what_changed(hass: HomeAssistant) -> None:
    """A script is started with the variables, so it can say what happened."""
    calls = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, ["script.notify_me"]).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == ["script.notify_me"]
    assert calls[0].data["variables"]["previous_label"] == "Eolo"
    assert calls[0].data["variables"]["label"] == "Iliad"


async def test_automations_and_scripts_are_started_apart(
    hass: HomeAssistant,
) -> None:
    """Two kinds of target, two services, one call each."""
    automations = async_mock_service(hass, "automation", "trigger")
    scripts = async_mock_service(hass, "script", "turn_on")
    await announcer_over(
        hass,
        ["automation.first", "script.second", "automation.third"],
    ).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert automations[0].data["entity_id"] == ["automation.first", "automation.third"]
    assert scripts[0].data["entity_id"] == ["script.second"]


async def test_nothing_hooked_calls_no_service(hass: HomeAssistant) -> None:
    """The quiet case has to stay quiet, not call a service with no target."""
    automations = async_mock_service(hass, "automation", "trigger")
    scripts = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, []).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert automations == []
    assert scripts == []


async def test_an_entity_of_any_other_kind_is_left_alone(
    hass: HomeAssistant,
) -> None:
    """Only automations and scripts are ever started, whatever is configured."""
    automations = async_mock_service(hass, "automation", "trigger")
    scripts = async_mock_service(hass, "script", "turn_on")
    lights = async_mock_service(hass, "light", "turn_on")
    await announcer_over(hass, ["light.kitchen"]).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert automations == []
    assert scripts == []
    assert lights == []


async def test_the_options_dialog_wins_over_what_setup_stored(
    hass: HomeAssistant,
) -> None:
    """Changing the target in the dialog has to change what actually starts."""
    calls = async_mock_service(hass, "automation", "trigger")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CHANGE_TARGETS: ["automation.the_old_one"]},
        options={CONF_CHANGE_TARGETS: ["automation.the_new_one"]},
    )
    entry.add_to_hass(hass)
    await HassAnnouncer(hass, entry).provider_changed(EOLO, ILIAD)
    await hass.async_block_till_done()

    assert calls[0].data["entity_id"] == ["automation.the_new_one"]
