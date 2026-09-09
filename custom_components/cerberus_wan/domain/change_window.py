"""The moving window of provider changes, and what it says about them.

Nothing here reads the clock: the current moment is always passed in, which is
what makes a twenty four hour window testable without waiting twenty four
hours.
"""

from __future__ import annotations

from datetime import datetime, timedelta

WINDOW = timedelta(hours=24)


class ChangeWindow:
    """The switchovers of the last day, and nothing older."""

    def __init__(
        self, moments: list[datetime] | None = None, window: timedelta = WINDOW
    ) -> None:
        """Start from what is already known.

        Args:
            moments: the changes already recorded.
            window: how far back the window reaches.
        """
        self._moments = sorted(moments or [])
        self._window = window

    @property
    def window(self) -> timedelta:
        """Return how far back this window reaches.

        Returns:
            The width of the window.
        """
        return self._window

    @property
    def last(self) -> datetime | None:
        """Return when the provider last changed.

        Returns:
            The most recent change held, or None when none is.
        """
        return self._moments[-1] if self._moments else None

    def record(self, moment: datetime) -> None:
        """Record a change.

        Args:
            moment: when the provider changed.
        """
        self._moments.append(moment)
        self._moments.sort()

    def adopt(self, moments: list[datetime]) -> None:
        """Take in changes recovered from a previous run.

        They are merged rather than assigned: a change can happen between the
        start of the integration and the moment the stored window comes back,
        and losing it would understate the count.

        Args:
            moments: the changes recovered.
        """
        self._moments = sorted(set(self._moments) | set(moments))

    def expire(self, now: datetime) -> bool:
        """Drop the changes that have left the window.

        Args:
            now: the current moment.

        Returns:
            True when something was dropped, so a caller knows whether the
            numbers it published are now out of date.
        """
        kept = [moment for moment in self._moments if moment > now - self._window]
        if len(kept) == len(self._moments):
            return False
        self._moments = kept
        return True

    def count(self, now: datetime) -> int:
        """Return how many changes the window holds.

        Args:
            now: the current moment.

        Returns:
            The number of changes inside the window.
        """
        return sum(1 for moment in self._moments if moment > now - self._window)

    def per_hour(self, now: datetime) -> float:
        """Return the moving average of changes per hour.

        The count is already limited to the window, so dividing it by the
        width of the window is the rate over that window and nothing else.

        Args:
            now: the current moment.

        Returns:
            The changes per hour, rounded to three decimals so that a single
            change in a day reads as 0.042 rather than as zero.
        """
        hours = self._window.total_seconds() / 3600
        if not hours:
            return 0.0
        return round(self.count(now) / hours, 3)

    def to_list(self) -> list[str]:
        """Render the window for storage.

        Returns:
            One ISO 8601 string per change, oldest first.
        """
        return [moment.isoformat() for moment in self._moments]

    @staticmethod
    def from_list(raw: list[str] | None) -> list[datetime]:
        """Read back what to_list wrote.

        Unreadable entries are skipped rather than raised: a corrupted record
        costs one change in the statistics, never an entity that fails to
        start.

        Args:
            raw: the stored strings, or None when there is nothing stored.

        Returns:
            The moments that could be read.
        """
        moments = []
        for entry in raw or []:
            try:
                moments.append(datetime.fromisoformat(entry))
            except (TypeError, ValueError):
                continue
        return moments

    def __len__(self) -> int:
        """Return how many changes are held, expired ones included.

        Returns:
            The number of moments held.
        """
        return len(self._moments)
