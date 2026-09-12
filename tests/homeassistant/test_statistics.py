"""Tests for the two numbers that only mean something over time.

A count of the last twenty four hours that starts from zero whenever Home
Assistant restarts is not a count of the last twenty four hours, and an entity
that rewrites the same number every fifteen seconds fills the recorder with
five thousand rows a day that say nothing. Both behaviours live entirely in
the Home Assistant side of the sensor, so neither can be reached from the
domain suite.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import async_get
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

PROVIDER_SENSOR = "sensor.cerberus_wan"
CHANGES_SENSOR = "sensor.cerberus_wan_changes_in_24_hours"
RATE_SENSOR = "sensor.cerberus_wan_changes_per_hour"

SCAN_INTERVAL = timedelta(seconds=15)


def ago(hours: float) -> str:
    """Return a moment in the past, written the way the window stores it.

    Args:
        hours: how long ago the change happened.

    Returns:
        The moment, as an ISO 8601 string.
    """
    return (dt_util.utcnow() - timedelta(hours=hours)).isoformat()


async def tick(hass: HomeAssistant, freezer) -> None:
    """Let one polling cycle happen.

    Args:
        hass: the running Home Assistant instance.
        freezer: the frozen clock to move forward.
    """
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def restore(hass: HomeAssistant, moments: list[str]) -> None:
    """Pretend the entity was holding these changes before the restart.

    Args:
        hass: the running Home Assistant instance.
        moments: the stored changes, as the entity would have written them.
    """
    mock_restore_cache_with_extra_data(
        hass,
        ((State(CHANGES_SENSOR, str(len(moments))), {"moments": moments}),),
    )


async def test_the_window_survives_a_restart(hass: HomeAssistant, entry, start) -> None:
    """A statistic that resets whenever Home Assistant does is a statistic
    that lies."""
    restore(hass, [ago(1), ago(2)])
    await start(entry, asn=35612)
    assert hass.states.get(CHANGES_SENSOR).state == "2"


async def test_changes_older_than_the_window_do_not_come_back(
    hass: HomeAssistant, entry, start
) -> None:
    """Coming back from a restart is not a reason to widen the last day."""
    restore(hass, [ago(1), ago(30)])
    assert hass.states.get(CHANGES_SENSOR) is None
    await start(entry, asn=35612)
    assert hass.states.get(CHANGES_SENSOR).state == "1"


async def test_an_unreadable_moment_costs_one_change_not_the_entity(
    hass: HomeAssistant, entry, start
) -> None:
    """A corrupted record must not be able to stop the sensor from starting."""
    restore(hass, ["not a date", ago(1)])
    await start(entry, asn=35612)
    assert hass.states.get(CHANGES_SENSOR).state == "1"


async def test_the_rate_is_computed_over_the_window_that_came_back(
    hass: HomeAssistant, entry, start
) -> None:
    """Both statistics read the same window, so both have to be restored."""
    restore(hass, [ago(1), ago(2)])
    await start(entry, asn=35612)
    assert hass.states.get(RATE_SENSOR).state == "0.083"


async def test_when_the_provider_last_changed_comes_back_too(
    hass: HomeAssistant, entry, start
) -> None:
    """The count alone does not say when, which is half of what is asked."""
    moments = [ago(2), ago(1)]
    restore(hass, moments)
    await start(entry, asn=35612)
    attributes = hass.states.get(CHANGES_SENSOR).attributes
    assert attributes["last_change"] == moments[-1]
    assert attributes["window_hours"] == 24


async def test_a_statistic_is_not_rewritten_when_it_does_not_move(
    hass: HomeAssistant, entry, start, freezer
) -> None:
    """The poll runs every fifteen seconds and the count is almost always the
    same number: writing it anyway would be five thousand rows a day of
    nothing.

    The first poll after startup publishes regardless, because nothing has
    been published yet to compare against. It is the polls after it that have
    to stay quiet, so the window measured here starts from the second one.
    """
    await start(entry, asn=35612)
    await tick(hass, freezer)

    provider_before = hass.states.get(PROVIDER_SENSOR).last_reported
    changes_before = hass.states.get(CHANGES_SENSOR).last_reported
    rate_before = hass.states.get(RATE_SENSOR).last_reported

    await tick(hass, freezer)

    assert hass.states.get(CHANGES_SENSOR).last_reported == changes_before
    assert hass.states.get(RATE_SENSOR).last_reported == rate_before
    assert hass.states.get(PROVIDER_SENSOR).last_reported > provider_before


async def test_a_statistic_is_rewritten_as_soon_as_it_moves(
    hass: HomeAssistant, entry, start, freezer
) -> None:
    """Staying quiet must not turn into staying quiet about a real change."""
    restore(hass, [ago(23.99)])
    await start(entry, asn=35612)
    await tick(hass, freezer)
    assert hass.states.get(CHANGES_SENSOR).state == "1"

    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(CHANGES_SENSOR).state == "0"


async def test_the_stored_window_does_not_grow_across_restarts(
    hass: HomeAssistant, entry, start
) -> None:
    """The count filters by window on the way out, so an expired change left
    in the record would never show. It would still be written down again at
    every shutdown, and the record of an installation that restarts often
    would grow without ever being read.
    """
    recent, expired = ago(1), ago(30)
    restore(hass, [recent, expired])
    await start(entry, asn=35612)
    await async_mock_restore_state_shutdown_restart(hass)

    stored = async_get(hass).last_states[CHANGES_SENSOR]
    assert stored.extra_data.as_dict()["moments"] == [recent]


def restore_timeline(hass: HomeAssistant, segments: list[list[str]]) -> None:
    """Pretend the provider sensor was holding these segments before the restart.

    Args:
        hass: the running Home Assistant instance.
        segments: the stored segments, as the entity would have written them.
    """
    mock_restore_cache_with_extra_data(
        hass,
        ((State(PROVIDER_SENSOR, "Eolo"), {"segments": segments}),),
    )


async def test_the_shares_survive_a_restart(hass: HomeAssistant, entry, start) -> None:
    """Without this every provider would read as a share of the seconds since
    the restart, which is a number about Home Assistant and not about the
    line."""
    restore_timeline(hass, [[ago(4), "Eolo"], [ago(3), "Iliad"]])
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_iliad").state == "75.0"
    assert hass.states.get("sensor.cerberus_wan_eolo").state == "25.0"


async def test_the_segment_that_was_open_keeps_its_label(
    hass: HomeAssistant, entry, start
) -> None:
    """The line is not known to have moved while nobody was watching."""
    restore_timeline(hass, [[ago(4), "Eolo"]])
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_eolo").state == "100.0"
    assert hass.states.get(PROVIDER_SENSOR).attributes["covered_hours"] == 4.0


async def test_an_unreadable_segment_costs_one_segment_not_the_entity(
    hass: HomeAssistant, entry, start
) -> None:
    """A corrupted record must not be able to stop the sensor from starting."""
    restore_timeline(hass, [["not a date", "Eolo"], [ago(2), "Iliad"]])
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_iliad").state == "100.0"


async def test_the_stored_timeline_does_not_grow_across_restarts(
    hass: HomeAssistant, entry, start
) -> None:
    """A segment that left the day would be written down again at every
    shutdown, and the record of an installation that restarts often would grow
    without ever being read.

    The oldest one here is dropped; the one before it survives even though it
    also began outside the day, because it is the segment still running when
    the day began.
    """
    ancient, covering, recent = ago(72), ago(48), ago(1)
    restore_timeline(hass, [[ancient, "Eolo"], [covering, "Iliad"], [recent, "Eolo"]])
    await start(entry, asn=35612)
    await async_mock_restore_state_shutdown_restart(hass)

    stored = async_get(hass).last_states[PROVIDER_SENSOR]
    segments = stored.extra_data.as_dict()["segments"]
    assert [moment for moment, _ in segments] == [covering, recent]
