"""Tests for the service that decides which provider is carrying traffic."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from domain import MonitorSettings, ProviderTable, WanMonitor
from domain.asn_cache import REFRESH
from fakes import FakeListener, FakeProbe, FakeRegistry, FakeStore, FrozenClock

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@dataclass
class Rig:
    """A monitor and the fakes it was built over."""

    monitor: WanMonitor
    probe: FakeProbe
    registry: FakeRegistry
    clock: FrozenClock
    store: FakeStore
    listener: FakeListener

    async def observe(self):
        """Run one observation.

        Returns:
            The observation the monitor produced.
        """
        return await self.monitor.observe()


def build(address, known=None, table=None, stored=None) -> Rig:
    """Assemble a monitor over fakes.

    Args:
        address: what the probe should report.
        known: what the registry should know.
        table: the provider table, empty when not given.
        stored: the table of addresses supposedly already stored.

    Returns:
        The rig, so a test can move the clock and count the questions.
    """
    probe = FakeProbe(address)
    registry = FakeRegistry(known)
    clock = FrozenClock(MOMENT)
    store = FakeStore(stored)
    listener = FakeListener()
    monitor = WanMonitor(
        probe=probe,
        registry=registry,
        clock=clock,
        settings=MonitorSettings(
            table=table or ProviderTable(),
            disconnected_label="Disconnected",
            unknown_label="Unknown",
        ),
        store=store,
        listener=listener,
    )
    return Rig(monitor, probe, registry, clock, store, listener)


async def test_reports_the_configured_label_for_a_known_network() -> None:
    """A mapped network is reported by the name its owner chose."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    observation = await rig.observe()
    assert observation.label == "Eolo"
    assert observation.asn.number == 35612


async def test_reports_the_unknown_label_for_an_unmapped_network() -> None:
    """Traffic gets out, but nobody said what to call this provider."""
    rig = build("1.2.3.4", {"1.2.3.4": 51207}, ProviderTable({"35612": "Eolo"}))
    assert (await rig.observe()).label == "Unknown"


async def test_reports_disconnected_when_nothing_gets_out() -> None:
    """No address means no traffic, which is not the same as unknown."""
    rig = build(None)
    observation = await rig.observe()
    assert observation.label == "Disconnected"
    assert not observation.connected


async def test_does_not_ask_who_announces_an_address_there_is_not() -> None:
    """A disconnected line must not produce a lookup that cannot succeed."""
    rig = build(None)
    await rig.observe()
    assert rig.registry.asked == []


async def test_the_first_reading_is_not_a_change() -> None:
    """Starting up is the beginning of the record, not a switchover."""
    assert not (await build("1.2.3.4").observe()).follows(None)


async def test_a_reading_is_a_change_when_the_label_moves() -> None:
    """The comparison is on the label: that is what a provider change is."""
    table = ProviderTable({"35612": "Eolo", "51207": "Iliad"})
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207}, table)
    before = await rig.observe()
    rig.probe.address = "5.6.7.8"
    assert (await rig.observe()).follows(before)


async def test_a_renewed_address_on_the_same_provider_is_not_a_change() -> None:
    """A provider that renews its address has not changed."""
    known = {"1.2.3.4": 35612, "1.2.3.9": 35612}
    rig = build("1.2.3.4", known, ProviderTable({"35612": "Eolo"}))
    before = await rig.observe()
    rig.probe.address = "1.2.3.9"
    assert not (await rig.observe()).follows(before)


async def test_the_address_is_asked_for_on_every_cycle() -> None:
    """That question is the whole point of the polling loop."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        await rig.observe()
    assert rig.probe.calls == 4


async def test_who_announces_it_is_asked_once_and_then_remembered() -> None:
    """The second lookup is the one the local table exists to remove."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        await rig.observe()
    assert rig.registry.asked == ["1.2.3.4"]


async def test_an_address_never_seen_before_is_looked_up() -> None:
    """A switchover has to be resolved, it cannot be answered from memory."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207})
    await rig.observe()
    rig.probe.address = "5.6.7.8"
    await rig.observe()
    assert rig.registry.asked == ["1.2.3.4", "5.6.7.8"]


async def test_an_answer_is_asked_again_once_it_has_aged_out() -> None:
    """Trust in a stored answer ends, otherwise a reassignment is invisible."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    await rig.observe()
    rig.clock.moment = MOMENT + REFRESH + timedelta(minutes=1)
    await rig.observe()
    assert rig.registry.asked == ["1.2.3.4", "1.2.3.4"]


async def test_what_was_learned_before_a_restart_is_not_asked_again() -> None:
    """A restart must not cost a lookup for an address already known."""
    warm = build("1.2.3.4", {"1.2.3.4": 35612})
    await warm.observe()

    cold = build("1.2.3.4", {"1.2.3.4": 35612}, stored=warm.store.payload)
    await cold.monitor.prime()
    await cold.observe()
    assert cold.registry.asked == []


async def test_the_table_is_written_only_when_it_learns_something() -> None:
    """Writing on every cycle would be four writes a minute, for nothing."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        await rig.observe()
    assert rig.store.writes == 1


async def test_a_switchover_is_counted_in_the_window() -> None:
    """The count is what the statistics sensors report."""
    table = ProviderTable({"35612": "Eolo", "51207": "Iliad"})
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207}, table)
    await rig.observe()
    rig.probe.address = "5.6.7.8"
    await rig.observe()
    assert rig.monitor.changes_last_day == 1


async def test_starting_up_is_not_counted_as_a_switchover() -> None:
    """Otherwise every restart would invent a change that never happened."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    await rig.observe()
    assert rig.monitor.changes_last_day == 0


async def test_a_line_that_does_not_move_counts_nothing() -> None:
    """Four observations of the same provider are not four changes."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    for _ in range(4):
        await rig.observe()
    assert rig.monitor.changes_last_day == 0


async def test_a_change_leaves_the_window_after_a_day() -> None:
    """The statistic is a moving day, not a total."""
    table = ProviderTable({"35612": "Eolo", "51207": "Iliad"})
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207}, table)
    await rig.observe()
    rig.probe.address = "5.6.7.8"
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=25)
    assert rig.monitor.expire_changes() is True
    assert rig.monitor.changes_last_day == 0


async def test_losing_the_line_is_a_change_like_any_other() -> None:
    """Falling off the network is exactly what somebody wants counted."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    await rig.observe()
    rig.probe.address = None
    await rig.observe()
    assert rig.monitor.changes_last_day == 1
    assert rig.monitor.current.label == "Disconnected"


async def test_the_listener_hears_a_switchover() -> None:
    """This is what starts whatever the entry hooked to the change."""
    table = ProviderTable({"35612": "Eolo", "51207": "Iliad"})
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207}, table)
    await rig.observe()
    rig.probe.address = "5.6.7.8"
    await rig.observe()
    assert rig.listener.heard == [("Eolo", "Iliad")]


async def test_the_listener_is_not_told_about_the_first_reading() -> None:
    """Starting Home Assistant must not fire everybody's automations."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    await rig.observe()
    assert rig.listener.heard == []


async def test_the_listener_is_not_told_when_nothing_moved() -> None:
    """Four identical readings a minute are not four switchovers."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    for _ in range(4):
        await rig.observe()
    assert rig.listener.heard == []


async def test_the_first_reading_opens_a_segment() -> None:
    """The start of the record is not a switchover, but it is a segment."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=1)
    assert rig.monitor.share_of("Eolo") == 100.0


async def test_the_share_follows_the_time_and_not_the_switchovers() -> None:
    """Three hours on one provider and one on the other is not half each."""
    rig = build(
        "1.2.3.4",
        {"1.2.3.4": 35612, "5.6.7.8": 51207},
        ProviderTable({"35612": "Eolo", "51207": "Iliad"}),
    )
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=3)
    rig.probe.address = "5.6.7.8"
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=4)

    assert rig.monitor.share_of("Eolo") == 75.0
    assert rig.monitor.share_of("Iliad") == 25.0


async def test_the_hours_on_record_are_published_beside_the_share() -> None:
    """A share of two hours has to be readable as a share of two hours."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=2)
    assert rig.monitor.covered_hours == 2.0


async def test_a_provider_nobody_named_still_holds_its_time() -> None:
    """The unknown label is a label: the day it took has to go somewhere."""
    rig = build("1.2.3.4", {"1.2.3.4": 51207}, ProviderTable({"35612": "Eolo"}))
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=1)
    assert rig.monitor.share_of("Unknown") == 100.0


async def test_the_sweep_drops_segments_that_left_the_day() -> None:
    """The shares are of the last day, so the record has to stop growing."""
    rig = build(
        "1.2.3.4",
        {"1.2.3.4": 35612, "5.6.7.8": 51207},
        ProviderTable({"35612": "Eolo", "51207": "Iliad"}),
    )
    await rig.observe()
    rig.clock.moment = MOMENT + timedelta(hours=1)
    rig.probe.address = "5.6.7.8"
    await rig.observe()

    rig.clock.moment = MOMENT + timedelta(hours=48)
    assert rig.monitor.expire_changes()
    assert rig.monitor.share_of("Iliad") == 100.0
