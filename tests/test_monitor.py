"""Tests for the service that decides which provider is carrying traffic."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from domain import MonitorSettings, ProviderTable, WanMonitor
from domain.asn_cache import REFRESH
from fakes import FakeProbe, FakeRegistry, FakeStore, FrozenClock

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@dataclass
class Rig:
    """A monitor and the fakes it was built over."""

    monitor: WanMonitor
    probe: FakeProbe
    registry: FakeRegistry
    clock: FrozenClock
    store: FakeStore

    def observe(self):
        """Run one observation.

        Returns:
            The observation the monitor produced.
        """
        return asyncio.run(self.monitor.observe())


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
    )
    return Rig(monitor, probe, registry, clock, store)


def test_reports_the_configured_label_for_a_known_network() -> None:
    """A mapped network is reported by the name its owner chose."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    observation = rig.observe()
    assert observation.label == "Eolo"
    assert observation.asn.number == 35612


def test_reports_the_unknown_label_for_an_unmapped_network() -> None:
    """Traffic gets out, but nobody said what to call this provider."""
    rig = build("1.2.3.4", {"1.2.3.4": 51207}, ProviderTable({"35612": "Eolo"}))
    assert rig.observe().label == "Unknown"


def test_reports_disconnected_when_nothing_gets_out() -> None:
    """No address means no traffic, which is not the same as unknown."""
    rig = build(None)
    observation = rig.observe()
    assert observation.label == "Disconnected"
    assert not observation.connected


def test_does_not_ask_who_announces_an_address_there_is_not() -> None:
    """A disconnected line must not produce a lookup that cannot succeed."""
    rig = build(None)
    rig.observe()
    assert rig.registry.asked == []


def test_the_first_reading_is_not_a_change() -> None:
    """Starting up is the beginning of the record, not a switchover."""
    assert not build("1.2.3.4").observe().follows(None)


def test_a_reading_is_a_change_when_the_label_moves() -> None:
    """The comparison is on the label: that is what a provider change is."""
    table = ProviderTable({"35612": "Eolo", "51207": "Iliad"})
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207}, table)
    before = rig.observe()
    rig.probe.address = "5.6.7.8"
    assert rig.observe().follows(before)


def test_a_renewed_address_on_the_same_provider_is_not_a_change() -> None:
    """A provider that renews its address has not changed."""
    known = {"1.2.3.4": 35612, "1.2.3.9": 35612}
    rig = build("1.2.3.4", known, ProviderTable({"35612": "Eolo"}))
    before = rig.observe()
    rig.probe.address = "1.2.3.9"
    assert not rig.observe().follows(before)


def test_the_address_is_asked_for_on_every_cycle() -> None:
    """That question is the whole point of the polling loop."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        rig.observe()
    assert rig.probe.calls == 4


def test_who_announces_it_is_asked_once_and_then_remembered() -> None:
    """The second lookup is the one the local table exists to remove."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        rig.observe()
    assert rig.registry.asked == ["1.2.3.4"]


def test_an_address_never_seen_before_is_looked_up() -> None:
    """A switchover has to be resolved, it cannot be answered from memory."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612, "5.6.7.8": 51207})
    rig.observe()
    rig.probe.address = "5.6.7.8"
    rig.observe()
    assert rig.registry.asked == ["1.2.3.4", "5.6.7.8"]


def test_an_answer_is_asked_again_once_it_has_aged_out() -> None:
    """Trust in a stored answer ends, otherwise a reassignment is invisible."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    rig.observe()
    rig.clock.moment = MOMENT + REFRESH + timedelta(minutes=1)
    rig.observe()
    assert rig.registry.asked == ["1.2.3.4", "1.2.3.4"]


def test_what_was_learned_before_a_restart_is_not_asked_again() -> None:
    """A restart must not cost a lookup for an address already known."""
    warm = build("1.2.3.4", {"1.2.3.4": 35612})
    warm.observe()

    cold = build("1.2.3.4", {"1.2.3.4": 35612}, stored=warm.store.payload)
    asyncio.run(cold.monitor.prime())
    cold.observe()
    assert cold.registry.asked == []


def test_the_table_is_written_only_when_it_learns_something() -> None:
    """Writing on every cycle would be four writes a minute, for nothing."""
    rig = build("1.2.3.4", {"1.2.3.4": 35612})
    for _ in range(4):
        rig.observe()
    assert rig.store.writes == 1
