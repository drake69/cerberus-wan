"""Which provider carried the traffic, and for how long.

The change window next door answers when the provider moved. This answers what
it was and for how much of the day, which is a different question and needs a
different record: a moment is enough to count a switchover, but a share of the
day needs to know what came after it and until when.

Nothing here reads the clock: the current moment is always passed in, which is
what makes a share of the last twenty four hours testable without waiting
twenty four hours.
"""

from __future__ import annotations

from datetime import datetime, timedelta

WINDOW = timedelta(hours=24)

# The share is rounded to one decimal, which is about eighty seconds of a day.
# Finer than that would be a number that moves on every poll and says nothing
# new; coarser would hide a failover of a couple of minutes entirely.
PRECISION = 1

Entry = tuple[datetime, str]


class LabelTimeline:
    """The providers of the last day, each with the time it was carrying.

    An entry says "from this moment the traffic was on this label". A segment
    therefore runs from its own entry to the next one, and the last segment
    runs to whatever moment the question is asked about.
    """

    def __init__(
        self, entries: list[Entry] | None = None, window: timedelta = WINDOW
    ) -> None:
        """Start from what is already known.

        Args:
            entries: the segments already recorded.
            window: how far back the timeline reaches.
        """
        self._entries = sorted(entries or [])
        self._collapse()
        self._window = window

    @property
    def window(self) -> timedelta:
        """Return how far back this timeline reaches.

        Returns:
            The width of the window.
        """
        return self._window

    def _collapse(self) -> None:
        """Drop entries that open a segment already open.

        Two consecutive entries with the same label are one segment written
        twice. They cannot come from record, which refuses them, but they can
        come from merging a restored timeline with a running one.
        """
        collapsed: list[Entry] = []
        for entry in self._entries:
            if collapsed and collapsed[-1][1] == entry[1]:
                continue
            collapsed.append(entry)
        self._entries = collapsed

    def record(self, moment: datetime, label: str) -> None:
        """Note that from this moment the traffic is on this label.

        Unlike the change window, the first reading is recorded: it is not a
        switchover, but it is the start of a segment, and a segment nobody
        opened is time attributed to nobody.

        Args:
            moment: when the label started carrying.
            label: what the provider is called.
        """
        if self._entries and self._entries[-1][1] == label:
            return
        self._entries.append((moment, label))
        self._entries.sort()

    def adopt(self, entries: list[Entry]) -> None:
        """Take in segments recovered from a previous run.

        They are merged rather than assigned, for the same reason the change
        window merges: the first observation of the new run lands before the
        stored timeline comes back, and assigning would throw it away.

        Args:
            entries: the segments recovered.
        """
        self._entries = sorted(set(self._entries) | set(entries))
        self._collapse()

    def expire(self, now: datetime) -> bool:
        """Drop the segments that have entirely left the window.

        The segment covering the start of the window is kept even though it
        began before it. It is still carrying part of the day, and dropping it
        would hand its share to nobody.

        Args:
            now: the current moment.

        Returns:
            True when something was dropped, so a caller knows the shares it
            published are now out of date.
        """
        start = now - self._window
        kept = [entry for entry in self._entries if entry[0] > start]
        covering = [entry for entry in self._entries if entry[0] <= start]
        if covering:
            kept.insert(0, covering[-1])
        if len(kept) == len(self._entries):
            return False
        self._entries = kept
        return True

    def seconds(self, now: datetime) -> dict[str, float]:
        """Return how long each label carried the traffic inside the window.

        Args:
            now: the current moment, which closes the last segment.

        Returns:
            The seconds held by each label, labels never seen omitted.
        """
        start = now - self._window
        totals: dict[str, float] = {}
        for index, (moment, label) in enumerate(self._entries):
            began = max(moment, start)
            ends = (
                self._entries[index + 1][0] if index + 1 < len(self._entries) else now
            )
            ended = min(ends, now)
            if ended <= began:
                continue
            totals[label] = totals.get(label, 0.0) + (ended - began).total_seconds()
        return totals

    def covered(self, now: datetime) -> float:
        """Return how much of the window this timeline can actually speak for.

        An installation running for two hours knows nothing about the other
        twenty two, and saying so is the difference between a share and a
        guess.

        Args:
            now: the current moment.

        Returns:
            The seconds of the window that are on the record.
        """
        return sum(self.seconds(now).values())

    def share(self, label: str, now: datetime) -> float:
        """Return the percentage of the recorded time spent on a label.

        The denominator is what the timeline covers, not the full window: on
        an installation started two hours ago the only honest answer is a
        percentage of those two hours. How much is covered is published beside
        the number rather than folded into it.

        Args:
            label: the provider to report on.
            now: the current moment.

        Returns:
            The percentage, or zero when there is nothing on the record.
        """
        totals = self.seconds(now)
        covered = sum(totals.values())
        if not covered:
            return 0.0
        return round(totals.get(label, 0.0) / covered * 100, PRECISION)

    @property
    def current(self) -> str | None:
        """Return the label of the segment still open.

        Returns:
            The label carrying the traffic, or None before the first record.
        """
        return self._entries[-1][1] if self._entries else None

    def to_list(self) -> list[list[str]]:
        """Render the timeline for storage.

        Returns:
            One [moment, label] pair per segment, oldest first, in forms that
            survive a round trip through JSON.
        """
        return [[moment.isoformat(), label] for moment, label in self._entries]

    @staticmethod
    def from_list(raw: list | None) -> list[Entry]:
        """Read back what to_list wrote.

        Unreadable entries are skipped rather than raised: a corrupted record
        costs one segment in the shares, never an entity that fails to start.

        Args:
            raw: the stored pairs, or None when there is nothing stored.

        Returns:
            The segments that could be read.
        """
        entries: list[Entry] = []
        for row in raw or []:
            try:
                moment, label = row
                entries.append((datetime.fromisoformat(moment), str(label)))
            except (TypeError, ValueError):
                continue
        return entries

    def __len__(self) -> int:
        """Return how many segments are held.

        Returns:
            The number of entries held.
        """
        return len(self._entries)
