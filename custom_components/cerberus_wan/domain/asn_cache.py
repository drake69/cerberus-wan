"""What is already known about an address, so it is not asked again.

An address does not change owner. Once the registry has said who announces
1.2.3.4, that answer holds until the address is handed to somebody else, which
happens on a scale of months and not of seconds. Keeping the answers here turns
the second lookup from something done on every cycle into something done when
an address is seen for the first time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .asn import Asn

# A known answer is trusted for a month. Reassignments happen, so the answer is
# not kept forever, but they happen slowly enough that a month of trust costs
# nothing and saves every lookup in between.
REFRESH = timedelta(days=30)

# A lookup that failed is retried within the hour instead. Without this the
# failure would either be retried on every cycle, which is the hot loop the
# table exists to avoid, or be trusted for a month, which would turn a moment
# of DNS trouble into thirty days of an unknown provider.
RETRY = timedelta(hours=1)

# An address not seen for two months is forgotten. Coming back costs one
# lookup, which is cheaper than carrying every address ever held.
FORGET = timedelta(days=60)


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """One answer, and when it was obtained."""

    asn: Asn | None
    checked_at: datetime

    def is_fresh(self, now: datetime) -> bool:
        """Report whether this answer can still be trusted.

        Args:
            now: the current moment.

        Returns:
            True while the answer is inside its lifetime, which is short for a
            failure and long for a resolved network.
        """
        lifetime = RETRY if self.asn is None else REFRESH
        return now - self.checked_at < lifetime


class AsnCache:
    """The local table of addresses and the networks announcing them."""

    def __init__(self, entries: dict[str, CacheEntry] | None = None) -> None:
        """Start from what is already known.

        Args:
            entries: the known answers, keyed by address.
        """
        self._entries = dict(entries or {})

    def fresh(self, address: str, now: datetime) -> CacheEntry | None:
        """Return the answer for an address while it can still be trusted.

        Args:
            address: the address being resolved.
            now: the current moment.

        Returns:
            The entry, or None when the address is unknown or its answer has
            aged out and has to be asked again.
        """
        entry = self._entries.get(address)
        if entry is None or not entry.is_fresh(now):
            return None
        return entry

    def remember(self, address: str, asn: Asn | None, now: datetime) -> None:
        """Record what the registry answered for an address.

        Failures are recorded too: knowing that an address could not be
        resolved a minute ago is what keeps the retry from happening on every
        cycle.

        Args:
            address: the address that was looked up.
            asn: the answer, or None when there was none.
            now: the moment of the lookup.
        """
        self._entries[address] = CacheEntry(asn=asn, checked_at=now)

    def forget_old(self, now: datetime) -> None:
        """Drop the addresses that have not been seen for a long time.

        Args:
            now: the current moment.
        """
        self._entries = {
            address: entry
            for address, entry in self._entries.items()
            if now - entry.checked_at < FORGET
        }

    @property
    def seen_asns(self) -> list[Asn]:
        """Return every network this table has resolved, most recent first.

        The table is keyed by address, but the address is only ever the way to
        reach the question that matters: which networks has this installation
        gone out through. Two addresses of one network answer once.

        Returns:
            The networks, newest first, without repeats. Addresses that could
            not be resolved contribute nothing: a lookup that did not answer is
            not a network.
        """
        answered = [entry for entry in self._entries.values() if entry.asn is not None]
        answered.sort(key=lambda entry: entry.checked_at, reverse=True)
        return list(dict.fromkeys(entry.asn for entry in answered))

    def __len__(self) -> int:
        """Return how many addresses are known.

        Returns:
            The number of entries held.
        """
        return len(self._entries)

    def to_dict(self) -> dict:
        """Render the table for storage.

        Returns:
            A mapping from address to the answer and its moment, in forms that
            survive a round trip through JSON.
        """
        return {
            address: {
                "asn": entry.asn.number if entry.asn else None,
                "checked_at": entry.checked_at.isoformat(),
            }
            for address, entry in self._entries.items()
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> AsnCache:
        """Read back a table written by to_dict.

        Unreadable rows are skipped rather than raised: a corrupted table costs
        one lookup per lost address, never an integration that refuses to
        start.

        Args:
            payload: the stored table, or None when there is nothing stored.

        Returns:
            The table, empty when nothing could be read.
        """
        entries: dict[str, CacheEntry] = {}
        for address, row in (payload or {}).items():
            try:
                number = row["asn"]
                entries[address] = CacheEntry(
                    asn=Asn(number) if number is not None else None,
                    checked_at=datetime.fromisoformat(row["checked_at"]),
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
        return cls(entries)
