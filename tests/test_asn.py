"""Tests for the autonomous system number value object."""

from domain import Asn


def test_accepts_the_forms_people_type() -> None:
    """Bare digits, the AS prefix and a spaced prefix all mean the same."""
    assert Asn.parse("35612") == Asn.parse("AS35612") == Asn.parse("as 35612")


def test_reads_a_prefix_whatever_its_case() -> None:
    """Nobody should have to know which case the parser prefers."""
    assert Asn.parse("As35612") == Asn(35612)


def test_refuses_what_is_not_a_number() -> None:
    """An unreadable line has to be skipped, so it must be recognisable."""
    assert Asn.parse("nonsense") is None
    assert Asn.parse("") is None


def test_the_key_is_the_bare_number() -> None:
    """The table is keyed by the number as text, and survives a config entry."""
    assert Asn(35612).key == "35612"


def test_the_directory_link_names_the_network() -> None:
    """The dialog offers the link so a human can decide what to call it."""
    assert Asn(35612).directory_url.endswith("AS35612")
