"""What the model needs from the outside world, and nothing more.

These are the only points where the domain touches anything it does not own.
Every one of them is implemented twice: once in the infrastructure package,
against DNS and the wall clock, and once in the tests, against a dictionary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .asn import Asn
from .transition import Transition


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


class CacheStore(Protocol):
    """Keeps the table of known addresses across a restart."""

    async def load(self) -> dict:
        """Return the stored table.

        Returns:
            The payload written by the last save, empty when there is none.
        """

    async def save(self, payload: dict) -> None:
        """Write the table.

        Args:
            payload: the table to store.
        """


class ChangeListener(Protocol):
    """Told when the reported provider moves, and free to do anything with it."""

    async def changed(self, transition: Transition) -> None:
        """React to a movement of the reported provider.

        Told about every movement and not only about a provider change: what to
        do with a line that dropped is a decision for whoever implements this,
        not for the model, and the movement says which kind it is.

        Args:
            transition: what moved, and what kind of movement it was.
        """


class Clock(Protocol):
    """Answers what time it is."""

    def now(self) -> datetime:
        """Return the current moment, with a time zone attached.

        Returns:
            The current moment.
        """
