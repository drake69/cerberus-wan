"""Tests for the local table of addresses and their networks."""

from datetime import UTC, datetime, timedelta

from domain import Asn, AsnCache
from domain.asn_cache import FORGET, REFRESH, RETRY

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def test_an_answer_is_trusted_for_a_month() -> None:
    """A month of trust is what removes the lookup from the cycle."""
    cache = AsnCache()
    cache.remember("1.2.3.4", Asn(35612), MOMENT)
    still_fresh = cache.fresh("1.2.3.4", MOMENT + REFRESH - timedelta(minutes=1))
    assert still_fresh.asn == Asn(35612)


def test_an_answer_older_than_a_month_has_to_be_asked_again() -> None:
    """Addresses do get reassigned, so the trust has to end somewhere."""
    cache = AsnCache()
    cache.remember("1.2.3.4", Asn(35612), MOMENT)
    assert cache.fresh("1.2.3.4", MOMENT + REFRESH + timedelta(minutes=1)) is None


def test_an_unknown_address_is_not_an_answer() -> None:
    """The first time an address is seen there is nothing to answer with."""
    assert AsnCache().fresh("1.2.3.4", MOMENT) is None


def test_a_failed_lookup_is_remembered_only_briefly() -> None:
    """Long enough to stop a retry every fifteen seconds, short enough that a
    moment of DNS trouble does not become a month of unknown provider."""
    cache = AsnCache()
    cache.remember("1.2.3.4", None, MOMENT)
    assert cache.fresh("1.2.3.4", MOMENT + RETRY - timedelta(minutes=1)) is not None
    assert cache.fresh("1.2.3.4", MOMENT + RETRY + timedelta(minutes=1)) is None


def test_addresses_nobody_has_seen_for_long_are_dropped() -> None:
    """Otherwise the table carries every address ever held, forever."""
    cache = AsnCache()
    cache.remember("1.2.3.4", Asn(35612), MOMENT)
    cache.remember("5.6.7.8", Asn(51207), MOMENT + FORGET)
    cache.forget_old(MOMENT + FORGET + timedelta(minutes=1))
    assert len(cache) == 1
    assert cache.fresh("5.6.7.8", MOMENT + FORGET + timedelta(minutes=1)) is not None


def test_the_table_survives_a_round_trip_through_storage() -> None:
    """What is written has to be readable, including a remembered failure."""
    cache = AsnCache()
    cache.remember("1.2.3.4", Asn(35612), MOMENT)
    cache.remember("5.6.7.8", None, MOMENT)
    restored = AsnCache.from_dict(cache.to_dict())
    assert restored.fresh("1.2.3.4", MOMENT).asn == Asn(35612)
    assert restored.fresh("5.6.7.8", MOMENT).asn is None


def test_a_corrupted_row_costs_one_address_and_not_the_startup() -> None:
    """An unreadable table must not keep the integration from starting."""
    restored = AsnCache.from_dict(
        {
            "1.2.3.4": {"asn": 35612, "checked_at": MOMENT.isoformat()},
            "5.6.7.8": {"asn": 51207, "checked_at": "not a date"},
            "9.9.9.9": "not a row at all",
        }
    )
    assert len(restored) == 1


def test_nothing_stored_is_an_empty_table() -> None:
    """A first run has no file to read."""
    assert len(AsnCache.from_dict(None)) == 0
