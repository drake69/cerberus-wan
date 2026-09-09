"""Stand ins for the three protocols the domain depends on.

Their existence is the point of the ports: the whole model runs here against a
dictionary and a fixed moment, with no network and no Home Assistant.
"""

from __future__ import annotations

from datetime import datetime

from domain import Asn


class FakeProbe:
    """An address probe that answers whatever it was told to answer."""

    def __init__(self, address: str | None) -> None:
        """Record the answer to give.

        Args:
            address: what to report as the public address.
        """
        self.address = address
        self.calls = 0

    async def public_address(self) -> str | None:
        """Return the configured address.

        Returns:
            The address, or None.
        """
        self.calls += 1
        return self.address


class FakeRegistry:
    """A registry that answers from a dictionary and counts the questions."""

    def __init__(self, known: dict[str, int] | None = None) -> None:
        """Record what is known about which address.

        Args:
            known: mapping from address to autonomous system number.
        """
        self.known = known or {}
        self.asked: list[str] = []

    async def announcing_asn(self, address: str) -> Asn | None:
        """Return the network announcing the address.

        Args:
            address: the address to look up.

        Returns:
            The number, or None when the address is not in the dictionary.
        """
        self.asked.append(address)
        number = self.known.get(address)
        return Asn(number) if number is not None else None


class FrozenClock:
    """A clock that reports the moment it was set to, until it is moved."""

    def __init__(self, moment: datetime) -> None:
        """Set the clock.

        Args:
            moment: the moment to report.
        """
        self.moment = moment

    def now(self) -> datetime:
        """Return the current moment.

        Returns:
            Whatever the clock was last set to.
        """
        return self.moment
