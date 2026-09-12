"""Tests that the component actually loads, and what it puts on the screen.

The domain suite proves the rules are right. This one proves Home Assistant
can start them: the platform is forwarded, the entities are created with the
names and the attributes the dashboard will show, and the entry unloads
cleanly. It is the part that no amount of domain testing can reach, because
the failures live in the wiring rather than in the rules.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

PROVIDER_SENSOR = "sensor.cerberus_wan"


async def test_the_entry_loads(hass: HomeAssistant, entry, start) -> None:
    """Nothing else in this file means anything if this one fails."""
    await start(entry, asn=35612)
    assert entry.state is ConfigEntryState.LOADED


async def test_the_provider_sensor_reports_the_configured_name(
    hass: HomeAssistant, entry, start
) -> None:
    """What the dashboard shows is the name chosen in the dialog."""
    await start(entry, asn=35612)
    assert hass.states.get(PROVIDER_SENSOR).state == "Eolo"


async def test_the_provider_sensor_publishes_the_evidence(
    hass: HomeAssistant, entry, start
) -> None:
    """The number behind the name has to be readable off the entity."""
    await start(entry, address="9.9.9.9", asn=35612)
    state = hass.states.get(PROVIDER_SENSOR)
    assert state.attributes["asn"] == 35612
    assert state.attributes["public_address"] == "9.9.9.9"


async def test_an_unmapped_network_is_reported_as_unknown(
    hass: HomeAssistant, entry, start
) -> None:
    """A network nobody named is honestly unnamed, and still shows its number."""
    await start(entry, asn=30722)
    state = hass.states.get(PROVIDER_SENSOR)
    assert state.state == "Unknown"
    assert state.attributes["asn"] == 30722


async def test_a_dead_line_is_reported_as_disconnected(
    hass: HomeAssistant, entry, start
) -> None:
    """No address means no traffic, which is not the same as unknown."""
    await start(entry, address=None)
    state = hass.states.get(PROVIDER_SENSOR)
    assert state.state == "Disconnected"
    assert state.attributes["asn"] is None


async def test_one_share_sensor_per_label(hass: HomeAssistant, entry, start) -> None:
    """Every label the configuration can produce gets its own percentage."""
    await start(entry, asn=35612)
    entities = {
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.startswith("sensor.cerberus_wan_")
    }
    assert "sensor.cerberus_wan_eolo" in entities
    assert "sensor.cerberus_wan_iliad" in entities
    assert "sensor.cerberus_wan_disconnected" in entities
    assert "sensor.cerberus_wan_unknown" in entities


async def test_the_only_provider_on_record_holds_the_whole_share(
    hass: HomeAssistant, entry, start
) -> None:
    """One segment on the record is the whole record, however short."""
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_eolo").state == "100.0"
    assert hass.states.get("sensor.cerberus_wan_iliad").state == "0.0"


async def test_the_share_says_whether_its_provider_is_the_one_carrying(
    hass: HomeAssistant, entry, start
) -> None:
    """The flag the percentage replaced has to stay readable somewhere."""
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_eolo").attributes["active"] is True
    assert hass.states.get("sensor.cerberus_wan_iliad").attributes["active"] is False


async def test_the_provider_sensor_says_how_much_day_is_on_record(
    hass: HomeAssistant, entry, start
) -> None:
    """A share of two hours is not a share of the day, and has to say so."""
    await start(entry, asn=35612)
    assert hass.states.get(PROVIDER_SENSOR).attributes["covered_hours"] == 0.0


async def test_the_statistics_start_from_an_empty_window(
    hass: HomeAssistant, entry, start
) -> None:
    """A first reading is the beginning of the record, not a switchover."""
    await start(entry, asn=35612)
    assert hass.states.get("sensor.cerberus_wan_changes_in_24_hours").state == "0"
    assert hass.states.get("sensor.cerberus_wan_changes_per_hour").state == "0.0"


async def test_the_entry_unloads_cleanly(hass: HomeAssistant, entry, start) -> None:
    """An entry that cannot be removed is an entry that cannot be reconfigured."""
    await start(entry, asn=35612)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
