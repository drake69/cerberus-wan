"""Tests for the composition root, against a real Home Assistant store.

The dialog answers "which networks have been seen" out of the same file the
monitor writes while it runs. Nothing in the domain suite can check that the
two halves agree on the format, because the format only exists once a real
store has written it.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.cerberus_wan.assembly import (
    STORAGE_KEY,
    STORAGE_VERSION,
    seen_networks,
)
from custom_components.cerberus_wan.domain import Asn


def store_holding(rows: dict) -> dict:
    """Return a stored payload shaped the way the cache writes it.

    Args:
        rows: the addresses and their answers.

    Returns:
        The payload as it sits in the storage file.
    """
    return {"version": STORAGE_VERSION, "key": STORAGE_KEY, "data": rows}


async def test_nothing_stored_offers_nothing(hass: HomeAssistant) -> None:
    """A first install has no history, and that is not an error."""
    assert await seen_networks(hass) == []


async def test_the_networks_come_back_newest_first(
    hass: HomeAssistant, hass_storage
) -> None:
    """The network just left is the one most likely to still need a name."""
    hass_storage[STORAGE_KEY] = store_holding(
        {
            "1.2.3.4": {"asn": 35612, "checked_at": "2026-09-01T12:00:00+00:00"},
            "5.6.7.8": {"asn": 51207, "checked_at": "2026-09-08T12:00:00+00:00"},
        }
    )
    assert await seen_networks(hass) == [Asn(51207), Asn(35612)]


async def test_a_corrupted_row_costs_one_network_not_the_dialog(
    hass: HomeAssistant, hass_storage
) -> None:
    """An unreadable file must open the form, not break it."""
    hass_storage[STORAGE_KEY] = store_holding(
        {
            "1.2.3.4": {"asn": 35612, "checked_at": "2026-09-01T12:00:00+00:00"},
            "5.6.7.8": {"asn": 51207, "checked_at": "not a date"},
        }
    )
    assert await seen_networks(hass) == [Asn(35612)]
