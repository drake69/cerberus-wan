"""Tests for the service that decides which provider is carrying traffic."""

import asyncio
from datetime import UTC, datetime

from domain import MonitorSettings, ProviderTable, WanMonitor
from fakes import FakeProbe, FakeRegistry, FrozenClock

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def build(address, known=None, table=None) -> tuple[WanMonitor, FakeRegistry]:
    """Assemble a monitor over fakes.

    Args:
        address: what the probe should report.
        known: what the registry should know.
        table: the provider table, empty when not given.

    Returns:
        The monitor and the registry, so a test can count the questions.
    """
    registry = FakeRegistry(known)
    monitor = WanMonitor(
        probe=FakeProbe(address),
        registry=registry,
        clock=FrozenClock(MOMENT),
        settings=MonitorSettings(
            table=table or ProviderTable(),
            disconnected_label="Disconnected",
            unknown_label="Unknown",
        ),
    )
    return monitor, registry


def test_reports_the_configured_label_for_a_known_network() -> None:
    """A mapped network is reported by the name its owner chose."""
    monitor, _ = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    observation = asyncio.run(monitor.observe())
    assert observation.label == "Eolo"
    assert observation.asn.number == 35612


def test_reports_the_unknown_label_for_an_unmapped_network() -> None:
    """Traffic gets out, but nobody said what to call this provider."""
    monitor, _ = build("1.2.3.4", {"1.2.3.4": 51207}, ProviderTable({"35612": "Eolo"}))
    assert asyncio.run(monitor.observe()).label == "Unknown"


def test_reports_disconnected_when_nothing_gets_out() -> None:
    """No address means no traffic, which is not the same as unknown."""
    monitor, _ = build(None)
    observation = asyncio.run(monitor.observe())
    assert observation.label == "Disconnected"
    assert not observation.connected


def test_does_not_ask_who_announces_an_address_there_is_not() -> None:
    """A disconnected line must not produce a lookup that cannot succeed."""
    monitor, registry = build(None)
    asyncio.run(monitor.observe())
    assert registry.asked == []


def test_the_first_reading_is_not_a_change() -> None:
    """Starting up is the beginning of the record, not a switchover."""
    monitor, _ = build("1.2.3.4")
    assert not asyncio.run(monitor.observe()).follows(None)


def test_a_reading_is_a_change_when_the_label_moves() -> None:
    """The comparison is on the label: that is what a provider change is."""
    first, _ = build("1.2.3.4", {"1.2.3.4": 35612}, ProviderTable({"35612": "Eolo"}))
    second, _ = build("5.6.7.8", {"5.6.7.8": 51207}, ProviderTable({"51207": "Iliad"}))
    before = asyncio.run(first.observe())
    after = asyncio.run(second.observe())
    assert after.follows(before)


def test_a_renewed_address_on_the_same_provider_is_not_a_change() -> None:
    """A provider that renews its address has not changed."""
    table = ProviderTable({"35612": "Eolo"})
    first, _ = build("1.2.3.4", {"1.2.3.4": 35612}, table)
    second, _ = build("1.2.3.9", {"1.2.3.9": 35612}, table)
    before = asyncio.run(first.observe())
    after = asyncio.run(second.observe())
    assert not after.follows(before)
