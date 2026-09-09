"""The wall clock, behind the Clock protocol."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Reads the machine clock, in UTC."""

    def now(self) -> datetime:
        """Return the current moment.

        Returns:
            The current moment, in UTC, with the time zone attached so that
            arithmetic across a restart cannot silently mix naive and aware
            values.
        """
        return datetime.now(UTC)
