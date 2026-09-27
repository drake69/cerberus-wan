"""Why the reported provider moved, decided once instead of guessed everywhere.

Until this module existed there was one signal, "the label moved", and four
different things produced it: a real failover, the line going down, the line
coming back, and a lookup that did not answer. Nothing told them apart, so an
automation hooked to a switchover ran on all four, and a counter of switchovers
counted all four. They are told apart here, once, and everything downstream
reads the answer instead of deciding again.

The rule, in the order it is applied:

    the announcing network is known and differs from the last known one
        -> a provider change, whatever happened in between
    the movement has the disconnected state at one of its ends
        -> a line change: the link dropped, or came back
    anything else
        -> the label moved without a verdict about the network

The first rule is deliberately compared against the last *resolved* reading and
not against the reading immediately before. A failover that happens while the
line is down reads as Eolo, disconnected, Vodafone: comparing Vodafone with
disconnected can only say "something moved", comparing it with Eolo says which
provider gave way to which.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .observation import Observation


class ChangeKind(Enum):
    """The three things that move the reported provider."""

    # The network announcing the traffic is not the one that announced it
    # before. This is the switchover whoever installed the integration cares
    # about.
    PROVIDER = "provider"

    # The line went down, or came back up on the provider it was already on.
    # A router that renegotiates its session produces two of these and no
    # provider change.
    LINK = "link"

    # The label moved, but no statement about the network can be made from it:
    # there is no answer yet to compare against, or the answer just arrived.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class Transition:
    """One movement of the reported provider, and what caused it."""

    kind: ChangeKind
    previous: Observation
    current: Observation

    @property
    def is_provider_change(self) -> bool:
        """Report whether the provider itself changed.

        Returns:
            True only for a change of announcing network.
        """
        return self.kind is ChangeKind.PROVIDER

    @property
    def is_outage(self) -> bool:
        """Report whether this movement is the line going down.

        The return of the line is a line change too, and counting both ends
        would make one interruption read as two.

        Returns:
            True when this is the moment the connection was lost.
        """
        return self.kind is ChangeKind.LINK and not self.current.connected


def classify(
    previous: Observation,
    current: Observation,
    last_resolved: Observation | None,
) -> Transition:
    """Say what kind of movement a pair of readings is.

    Args:
        previous: the reading before this one. Never None: the caller only
            asks once it knows the label moved, and at startup it does not
            move, it begins.
        current: the reading whose label differs from the one before.
        last_resolved: the most recent reading whose announcing network was
            known, from before this one, or None when there has never been
            one.

    Returns:
        The movement, classified.
    """
    if (
        current.resolved
        and last_resolved is not None
        and current.asn != last_resolved.asn
    ):
        kind = ChangeKind.PROVIDER
    elif not current.connected or not previous.connected:
        kind = ChangeKind.LINK
    else:
        kind = ChangeKind.UNRESOLVED
    return Transition(kind=kind, previous=previous, current=current)
