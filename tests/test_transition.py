"""Tests for the rule that says why the reported provider moved.

The rule used to be "the label moved", and four different things produced it.
These tests are the four things, told apart.
"""

from datetime import UTC, datetime

from domain import ChangeKind, classify
from domain.asn import Asn
from domain.observation import Observation

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def reading(label: str, number: int | None, address: str | None = "1.2.3.4"):
    """Build a reading without repeating the moment in every test.

    Args:
        label: what the reading reports.
        number: the announcing network, or None when it is not known.
        address: the public address, or None when nothing gets out.

    Returns:
        The reading.
    """
    return Observation(
        moment=MOMENT,
        address=address,
        asn=Asn(number) if number is not None else None,
        label=label,
    )


EOLO = reading("Eolo", 35612)
ILIAD = reading("Iliad", 51207, address="5.6.7.8")
HELD = reading("Eolo", None, address="1.2.3.9")
DOWN = reading("Disconnected", None, address=None)


def test_a_different_network_is_a_change_of_provider() -> None:
    """The one movement worth waking somebody up for."""
    assert classify(EOLO, ILIAD, EOLO).kind is ChangeKind.PROVIDER


def test_losing_the_line_is_a_line_change() -> None:
    """Nothing was handed to anybody: the line simply went."""
    assert classify(EOLO, DOWN, EOLO).kind is ChangeKind.LINK


def test_coming_back_on_the_same_network_is_a_line_change() -> None:
    """The other end of the same interruption, and still no failover."""
    back = reading("Eolo", 35612, address="1.2.3.9")
    assert classify(DOWN, back, EOLO).kind is ChangeKind.LINK


def test_coming_back_on_another_network_is_a_change_of_provider() -> None:
    """A failover through a gap is a failover, not a line coming back.

    This is why the comparison is against the last reading that had a network
    and not against the reading immediately before: that one is the gap, and
    the gap can only say that something moved.
    """
    assert classify(DOWN, ILIAD, EOLO).kind is ChangeKind.PROVIDER


def test_a_network_that_cannot_be_named_yet_claims_nothing() -> None:
    """No verdict, so no statement about the provider either way."""
    assert classify(EOLO, HELD, EOLO).kind is ChangeKind.UNRESOLVED


def test_with_no_network_ever_resolved_nothing_can_be_a_failover() -> None:
    """The first answer has nothing behind it to have changed from."""
    assert classify(HELD, EOLO, None).kind is ChangeKind.UNRESOLVED
    assert classify(DOWN, EOLO, None).kind is ChangeKind.LINK


def test_only_the_moment_the_line_is_lost_counts_as_an_outage() -> None:
    """Counting the return as well would report every outage twice."""
    back = reading("Eolo", 35612, address="1.2.3.9")
    assert classify(EOLO, DOWN, EOLO).is_outage
    assert not classify(DOWN, back, EOLO).is_outage


def test_a_change_of_provider_is_never_an_outage() -> None:
    """The two counters must not both move on the same movement."""
    movement = classify(DOWN, ILIAD, EOLO)
    assert movement.is_provider_change
    assert not movement.is_outage


def test_the_movement_carries_both_readings() -> None:
    """Whoever is told has to be able to say what it was and what it became."""
    movement = classify(EOLO, ILIAD, EOLO)
    assert movement.previous is EOLO
    assert movement.current is ILIAD
