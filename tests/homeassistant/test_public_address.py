"""Tests for the address entity, and for what makes it different.

The address the traffic goes out from is already an attribute of the provider
sensor, so what is worth checking here is what an entity does that an attribute
cannot: hold a history worth plotting, stay quiet while nothing happens, and
move on its own when the line renews its address without changing provider.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.cerberus_wan.domain import Asn

PROBE = "custom_components.cerberus_wan.assembly.DnsAddressProbe"
REGISTRY = "custom_components.cerberus_wan.assembly.CymruAsnRegistry"

ADDRESS_SENSOR = "sensor.cerberus_wan_public_address"
PROVIDER_SENSOR = "sensor.cerberus_wan"
CHANGES_SENSOR = "sensor.cerberus_wan_changes_in_24_hours"

SCAN_INTERVAL = timedelta(seconds=15)


class MovingProbe:
    """Answers with whatever address the test last put on it."""

    def __init__(self, address: str | None) -> None:
        """Start out on one address.

        Args:
            address: the address to report until the test changes it.
        """
        self.address = address

    async def public_address(self) -> str | None:
        """Return the address the outside world would see right now.

        Returns:
            The address currently set on this probe.
        """
        return self.address


class FixedRegistry:
    """Answers with the same network whatever the address is.

    Which is the point: a line that renews its address is still the same
    provider, and that is the case these tests are built around.
    """

    def __init__(self, asn: int) -> None:
        """Remember the network to report.

        Args:
            asn: the number announcing every address.
        """
        self._asn = Asn(asn)

    async def announcing_asn(self, address: str) -> Asn:
        """Return the network announcing an address.

        Args:
            address: the address being resolved, ignored here.

        Returns:
            The network given at construction.
        """
        return self._asn


@pytest.fixture(name="moving")
def moving_line(hass: HomeAssistant):
    """Return a way to start an entry over a line that can renew its address.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        An awaitable taking the entry and the address to start on, and giving
        back the probe so the test can move the line under it.
    """

    async def run(entry, address: str | None = "1.2.3.4", asn: int = 35612):
        """Set the entry up and hand back the probe it is now polling.

        Args:
            entry: the entry to set up.
            address: the address the line starts on.
            asn: the number every address resolves to.

        Returns:
            The probe the running integration is holding.
        """
        probe = MovingProbe(address)
        with (
            patch(PROBE, return_value=probe),
            patch(REGISTRY, return_value=FixedRegistry(asn)),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
        return probe

    return run


async def tick(hass: HomeAssistant, freezer) -> None:
    """Let one polling cycle happen.

    Args:
        hass: the running Home Assistant instance.
        freezer: the frozen clock to move forward.
    """
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_the_address_is_published_as_an_entity_of_its_own(
    hass: HomeAssistant, entry, start
) -> None:
    """The address is an attribute of the provider sensor and, since it is
    also a thing people plot and trigger on, an entity as well.
    """
    await start(entry, address="1.2.3.4", asn=35612)

    assert hass.states.get(ADDRESS_SENSOR).state == "1.2.3.4"


async def test_the_address_is_unknown_and_not_a_label_when_nothing_gets_out(
    hass: HomeAssistant, entry, start
) -> None:
    """An entity named after an address holds an address or nothing at all.

    Which provider is carrying is the other question, and the provider sensor
    is where it is answered, with the disconnected label. Repeating that label
    here would hand every template reading the address a word to parse.
    """
    await start(entry, address=None)

    assert hass.states.get(ADDRESS_SENSOR).state == "unknown"
    assert hass.states.get(PROVIDER_SENSOR).state == "Disconnected"


async def test_the_address_is_not_rewritten_while_the_line_keeps_it(
    hass: HomeAssistant, entry, start, freezer
) -> None:
    """A line can hold an address for months, and the poll runs every fifteen
    seconds: writing it each time would be five thousand rows a day of
    nothing, kept by the recorder for as long as it keeps anything.

    The first poll after startup publishes regardless, nothing having been
    published yet to compare against, so the window measured here starts from
    the second one.
    """
    await start(entry, address="1.2.3.4", asn=35612)
    await tick(hass, freezer)

    before = hass.states.get(ADDRESS_SENSOR).last_reported

    await tick(hass, freezer)

    assert hass.states.get(ADDRESS_SENSOR).last_reported == before


async def test_a_renewed_address_moves_this_entity_and_leaves_the_provider(
    hass: HomeAssistant, entry, moving, freezer
) -> None:
    """The case that makes the entity worth having.

    A line that renews its address has not changed provider: the label stands,
    the count of failovers stands, and until now nothing anywhere moved. The
    address entity is the one thing that does, which is what makes a renewal
    visible in the history at all.
    """
    probe = await moving(entry, address="1.2.3.4", asn=35612)
    await tick(hass, freezer)
    assert hass.states.get(ADDRESS_SENSOR).state == "1.2.3.4"

    probe.address = "1.2.3.9"
    await tick(hass, freezer)

    assert hass.states.get(ADDRESS_SENSOR).state == "1.2.3.9"
    assert hass.states.get(PROVIDER_SENSOR).state == "Eolo"
    assert hass.states.get(CHANGES_SENSOR).state == "0"
