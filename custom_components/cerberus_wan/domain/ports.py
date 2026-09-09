"""What the model needs from the outside world, and nothing more.

These are the only points where the domain touches anything it does not own.
Every one of them is implemented twice: once in the infrastructure package,
against DNS and the wall clock, and once in the tests, against a dictionary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .asn import Asn


class AddressProbe(Protocol):
    """Answers what the public address of this network is."""

    async def public_address(self) -> str | None:
        """Return the address the outside world sees.

        Returns:
            The address, or None when nothing gets out. None means
            disconnected, not "the lookup failed": if the question cannot
            leave the network, neither can the traffic.
        """


class AsnRegistry(Protocol):
    """Answers which network announces an address."""

    async def announcing_asn(self, address: str) -> Asn | None:
        """Return the autonomous system number announcing the address.

        Args:
            address: the public address to look up.

        Returns:
            The number, or None when it cannot be determined.
        """


class Clock(Protocol):
    """Answers what time it is."""

    def now(self) -> datetime:
        """Return the current moment, with a time zone attached.

        Returns:
            The current moment.
        """
