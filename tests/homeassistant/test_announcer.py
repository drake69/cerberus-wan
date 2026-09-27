"""Tests for what a movement of the reported provider sets in motion.

This is the only place in the integration that makes Home Assistant do
something on behalf of whoever configured it. Everything else reports; this
starts automations and scripts. It is worth checking that it starts exactly
what it was told to start, on exactly the kind of movement it was told to start
it on, and nothing next to either.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant, callback
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.cerberus_wan import (
    CONF_CHANGE_TARGETS,
    CONF_LINK_TARGETS,
    DOMAIN,
    EVENT_CONNECTION_CHANGED,
    EVENT_PROVIDER_CHANGED,
)
from custom_components.cerberus_wan.announcer import HassAnnouncer
from custom_components.cerberus_wan.domain import (
    Asn,
    ChangeKind,
    Observation,
    Transition,
)

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

EOLO = Observation(moment=MOMENT, address="1.2.3.4", asn=Asn(35612), label="Eolo")
ILIAD = Observation(moment=MOMENT, address="5.6.7.8", asn=Asn(51207), label="Iliad")
DOWN = Observation(moment=MOMENT, address=None, asn=None, label="Disconnected")
HELD = Observation(moment=MOMENT, address="1.2.3.9", asn=None, label="Eolo")

FAILOVER = Transition(kind=ChangeKind.PROVIDER, previous=EOLO, current=ILIAD)
OUTAGE = Transition(kind=ChangeKind.LINK, previous=EOLO, current=DOWN)
NO_VERDICT = Transition(kind=ChangeKind.UNRESOLVED, previous=EOLO, current=HELD)


def announcer_over(
    hass: HomeAssistant,
    targets: list[str] | None = None,
    link_targets: list[str] | None = None,
) -> HassAnnouncer:
    """Build an announcer bound to an entry hooked to the given targets.

    Args:
        hass: the running Home Assistant instance.
        targets: what the entry says to start on a change of provider.
        link_targets: what it says to start when the line drops or returns.

    Returns:
        The announcer under test.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHANGE_TARGETS: targets or [],
            CONF_LINK_TARGETS: link_targets or [],
        },
    )
    entry.add_to_hass(hass)
    return HassAnnouncer(hass, entry)


def _collector(events: list):
    """Return a listener that appends to a list, in the order events are fired.

    Marked as a callback on purpose: a listener that is not runs off the event
    loop, and then the order the events arrive in is not the order they were
    fired in, which is exactly what some of these tests are about.

    Args:
        events: the list to append to.

    Returns:
        The listener to register on the bus.
    """

    @callback
    def collect(event) -> None:
        events.append(event)

    return collect


@pytest.fixture(name="fired")
def fired_events(hass: HomeAssistant) -> list:
    """Collect the provider change events fired during a test.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The list the listener appends to, filled as the test runs.
    """
    events: list = []
    hass.bus.async_listen(EVENT_PROVIDER_CHANGED, _collector(events))
    return events


@pytest.fixture(name="seen")
def seen_events(hass: HomeAssistant) -> list:
    """Collect every movement event fired during a test.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The list the listener appends to, filled as the test runs.
    """
    events: list = []
    hass.bus.async_listen(EVENT_CONNECTION_CHANGED, _collector(events))
    return events


async def test_the_event_carries_what_changed(hass: HomeAssistant, fired: list) -> None:
    """Whoever writes their own trigger reads the change off the event."""
    await announcer_over(hass).changed(FAILOVER)
    await hass.async_block_till_done()

    assert len(fired) == 1
    assert fired[0].data["kind"] == "provider"
    assert fired[0].data["previous_label"] == "Eolo"
    assert fired[0].data["label"] == "Iliad"
    assert fired[0].data["previous_asn"] == 35612
    assert fired[0].data["asn"] == 51207
    assert fired[0].data["public_address"] == "5.6.7.8"
    assert fired[0].data["changed_at"] == MOMENT.isoformat()


async def test_the_event_says_which_entry_it_came_from(
    hass: HomeAssistant, fired: list
) -> None:
    """Two lines watched by two entries must be tellable apart."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await HassAnnouncer(hass, entry).changed(FAILOVER)
    await hass.async_block_till_done()

    assert fired[0].data["entry_id"] == entry.entry_id


async def test_a_line_that_dropped_does_not_fire_a_provider_change(
    hass: HomeAssistant, fired: list, seen: list
) -> None:
    """The whole point of two events.

    A line that goes down and comes back on the provider it was already on used
    to fire the same event as a failover, and an automation hooked to a failover
    had no way of telling the two apart.
    """
    await announcer_over(hass).changed(OUTAGE)
    await hass.async_block_till_done()

    assert fired == []
    assert len(seen) == 1
    assert seen[0].data["kind"] == "link"
    assert seen[0].data["label"] == "Disconnected"
    assert seen[0].data["asn"] is None
    assert seen[0].data["public_address"] is None


async def test_a_movement_with_no_verdict_is_reported_and_nothing_more(
    hass: HomeAssistant, fired: list, seen: list
) -> None:
    """Not knowing who is carrying the traffic is not news worth acting on."""
    automations = async_mock_service(hass, "automation", "trigger")
    await announcer_over(
        hass, ["automation.on_change"], ["automation.on_link"]
    ).changed(NO_VERDICT)
    await hass.async_block_till_done()

    assert fired == []
    assert len(seen) == 1
    assert seen[0].data["kind"] == "unresolved"
    assert automations == []


async def test_every_movement_is_reported_on_the_wider_event(
    hass: HomeAssistant, seen: list
) -> None:
    """Whoever wants to see everything has one event that shows everything."""
    announcer = announcer_over(hass)
    for movement in (FAILOVER, OUTAGE, NO_VERDICT):
        await announcer.changed(movement)
    await hass.async_block_till_done()

    assert [event.data["kind"] for event in seen] == [
        "provider",
        "link",
        "unresolved",
    ]


async def test_the_event_is_fired_even_with_nothing_hooked(
    hass: HomeAssistant, fired: list
) -> None:
    """Hooking nothing is a choice, not a reason to stay silent."""
    await announcer_over(hass).changed(FAILOVER)
    await hass.async_block_till_done()

    assert len(fired) == 1


async def test_an_automation_keeps_its_own_conditions(hass: HomeAssistant) -> None:
    """An automation that says "only at night" means it, started or not."""
    calls = async_mock_service(hass, "automation", "trigger")
    await announcer_over(hass, ["automation.call_me"]).changed(FAILOVER)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == ["automation.call_me"]
    assert calls[0].data["skip_condition"] is False


async def test_a_script_receives_what_changed(hass: HomeAssistant) -> None:
    """A script is started with the variables, so it can say what happened."""
    calls = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, ["script.notify_me"]).changed(FAILOVER)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == ["script.notify_me"]
    assert calls[0].data["variables"]["previous_label"] == "Eolo"
    assert calls[0].data["variables"]["label"] == "Iliad"


async def test_what_is_hooked_to_a_failover_ignores_the_line_dropping(
    hass: HomeAssistant,
) -> None:
    """The one line script somebody wrote to hear about failovers."""
    calls = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, ["script.notify_me"]).changed(OUTAGE)
    await hass.async_block_till_done()

    assert calls == []


async def test_what_is_hooked_to_the_line_ignores_a_failover(
    hass: HomeAssistant,
) -> None:
    """The two lists are separate in both directions, not just the one."""
    calls = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, link_targets=["script.line_went"]).changed(FAILOVER)
    await hass.async_block_till_done()

    assert calls == []


async def test_the_line_list_is_started_when_the_line_moves(
    hass: HomeAssistant,
) -> None:
    """And it receives the same description, so it can say which end it is."""
    calls = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass, link_targets=["script.line_went"]).changed(OUTAGE)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == ["script.line_went"]
    assert calls[0].data["variables"]["kind"] == "link"
    assert calls[0].data["variables"]["label"] == "Disconnected"


async def test_automations_and_scripts_are_started_apart(
    hass: HomeAssistant,
) -> None:
    """Two kinds of target, two services, one call each."""
    automations = async_mock_service(hass, "automation", "trigger")
    scripts = async_mock_service(hass, "script", "turn_on")
    await announcer_over(
        hass,
        ["automation.first", "script.second", "automation.third"],
    ).changed(FAILOVER)
    await hass.async_block_till_done()

    assert automations[0].data["entity_id"] == ["automation.first", "automation.third"]
    assert scripts[0].data["entity_id"] == ["script.second"]


async def test_nothing_hooked_calls_no_service(hass: HomeAssistant) -> None:
    """The quiet case has to stay quiet, not call a service with no target."""
    automations = async_mock_service(hass, "automation", "trigger")
    scripts = async_mock_service(hass, "script", "turn_on")
    await announcer_over(hass).changed(FAILOVER)
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
    await announcer_over(hass, ["light.kitchen"]).changed(FAILOVER)
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
    await HassAnnouncer(hass, entry).changed(FAILOVER)
    await hass.async_block_till_done()

    assert calls[0].data["entity_id"] == ["automation.the_new_one"]
