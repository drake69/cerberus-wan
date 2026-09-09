"""What the monitor saw, at one moment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .asn import Asn


@dataclass(frozen=True, slots=True)
class Observation:
    """One reading of the network: immutable, and complete on its own."""

    moment: datetime
    address: str | None
    asn: Asn | None
    label: str

    @property
    def connected(self) -> bool:
        """Report whether anything gets out.

        Returns:
            True when an address was resolved.
        """
        return self.address is not None

    def follows(self, previous: Observation | None) -> bool:
        """Report whether this reading is a change of provider.

        The comparison is on the label and not on the address: a provider that
        renews its address has not changed, and two networks sharing a label
        are one provider as far as whoever configured it is concerned.

        Args:
            previous: the reading before this one, or None at startup.

        Returns:
            True when the label moved. False at startup, because the first
            reading is not a change, it is the beginning of the record.
        """
        return previous is not None and previous.label != self.label
