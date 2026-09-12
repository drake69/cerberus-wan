"""Fixtures for the tests that run against a real Home Assistant.

Everything here costs a running instance, which is why it is a directory of
its own: the domain tests next door stay as fast as they were.

The network is replaced at the composition root rather than inside the
sensors, so that what is under test is the wiring Home Assistant will actually
use, minus the only part of it that needs a network.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cerberus_wan import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DOMAIN,
)
from custom_components.cerberus_wan.domain import Asn

PROBE = "custom_components.cerberus_wan.assembly.DnsAddressProbe"
REGISTRY = "custom_components.cerberus_wan.assembly.CymruAsnRegistry"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the component out of custom_components.

    Args:
        enable_custom_integrations: the harness fixture doing the work.
    """
    return


class FakeProbe:
    """Answers with a fixed address instead of asking OpenDNS."""

    def __init__(self, address: str | None) -> None:
        """Remember what to answer.

        Args:
            address: the address to report, or None for a dead line.
        """
        self._address = address

    async def public_address(self) -> str | None:
        """Return the address the outside world would see.

        Returns:
            The address given at construction.
        """
        return self._address


class FakeRegistry:
    """Answers with a fixed network instead of asking Cymru."""

    def __init__(self, asn: Asn | None) -> None:
        """Remember what to answer.

        Args:
            asn: the network to report, or None when it cannot be resolved.
        """
        self._asn = asn

    async def announcing_asn(self, address: str) -> Asn | None:
        """Return the network announcing an address.

        Args:
            address: the address being resolved, ignored here.

        Returns:
            The network given at construction.
        """
        return self._asn


@pytest.fixture(name="entry")
def provider_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an entry holding two named providers, not yet started.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The entry, already known to Home Assistant.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cerberus WAN",
        data={
            CONF_PROVIDERS: {"35612": "Eolo", "51207": "Iliad"},
            CONF_DISCONNECTED_LABEL: "Disconnected",
            CONF_UNKNOWN_LABEL: "Unknown",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(name="start")
def start_entry(hass: HomeAssistant):
    """Return a way to set an entry up over a network that answers to order.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        An awaitable taking the entry, the address to report and the number to
        resolve it to.
    """

    async def run(entry, address: str | None = "1.2.3.4", asn: int | None = None):
        """Set the entry up and wait for it to settle.

        Args:
            entry: the entry to set up.
            address: what the probe should report.
            asn: the number the registry should report, or None.
        """
        with (
            patch(PROBE, return_value=FakeProbe(address)),
            patch(REGISTRY, return_value=FakeRegistry(Asn(asn) if asn else None)),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

    return run
