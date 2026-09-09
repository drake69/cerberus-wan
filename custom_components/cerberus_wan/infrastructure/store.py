"""The table of known addresses, kept wherever the handle it is given points.

The storage handle is passed in rather than built here: this adapter needs
something that loads and that can defer a write, and does not need to know
whose storage directory it is writing into.
"""

from __future__ import annotations

# The table changes only when a new address is seen, which is rare, but the
# write is deferred anyway: a switchover is exactly the moment the machine has
# other things to do.
SAVE_DELAY = 60.0


class DelayedCacheStore:
    """Reads the table now, writes it a little later."""

    def __init__(self, store, delay: float = SAVE_DELAY) -> None:
        """Bind the adapter to a storage handle.

        Args:
            store: something offering async_load and async_delay_save, which
                is what a Home Assistant Store offers.
            delay: seconds to wait before the write actually happens.
        """
        self._store = store
        self._delay = delay

    async def load(self) -> dict:
        """Return the stored table.

        Returns:
            The payload written by the last save, empty on a first run or when
            the file is gone.
        """
        return await self._store.async_load() or {}

    async def save(self, payload: dict) -> None:
        """Schedule the table to be written.

        Args:
            payload: the table to store.
        """
        self._store.async_delay_save(lambda: payload, self._delay)
