"""Telling Home Assistant that the reported provider moved.

This is the Home Assistant side of the ChangeListener port. Two things happen
on a movement, and they answer two different needs: an event is fired, for
whoever wants to write their own trigger and read what changed, and whatever
the entry hooked to that kind of movement is started, for whoever just wants an
automation to run and does not want to write a trigger at all.

Two events and two lists of things to start, because a failover and a line that
renegotiated its session are not the same news. Whoever asked to hear about a
failover hears about failovers only.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import (
    CONF_CHANGE_TARGETS,
    CONF_LINK_TARGETS,
    EVENT_CONNECTION_CHANGED,
    EVENT_PROVIDER_CHANGED,
    setting,
)
from .domain import ChangeKind, Transition

AUTOMATION_PREFIX = "automation."
SCRIPT_PREFIX = "script."

# Which list of automations and scripts each kind of movement starts. A
# movement with no verdict about the network starts nothing: it is not news
# that anything happened, it is the admission that the answer is a couple of
# minutes late.
TARGETS_BY_KIND = {
    ChangeKind.PROVIDER: CONF_CHANGE_TARGETS,
    ChangeKind.LINK: CONF_LINK_TARGETS,
}


def describe(transition: Transition) -> dict:
    """Render a movement as the data an automation can read.

    Args:
        transition: what moved, and what kind of movement it was.

    Returns:
        What the event carries, and what a script receives as variables.
    """
    previous = transition.previous
    current = transition.current
    return {
        "kind": transition.kind.value,
        "previous_label": previous.label,
        "label": current.label,
        "previous_asn": previous.asn.number if previous.asn else None,
        "asn": current.asn.number if current.asn else None,
        "public_address": current.address,
        "changed_at": current.moment.isoformat(),
    }


class HassAnnouncer:
    """Fires the events, and starts whatever was hooked to this kind of change."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Bind the announcer to the entry whose settings it obeys.

        Args:
            hass: the running Home Assistant instance.
            entry: the config entry holding what to start.
        """
        self._hass = hass
        self._entry = entry

    async def changed(self, transition: Transition) -> None:
        """Announce a movement of the reported provider.

        Args:
            transition: what moved, and what kind of movement it was.
        """
        payload = describe(transition)
        payload["entry_id"] = self._entry.entry_id

        self._hass.bus.async_fire(EVENT_CONNECTION_CHANGED, payload)
        if transition.is_provider_change:
            self._hass.bus.async_fire(EVENT_PROVIDER_CHANGED, payload)

        key = TARGETS_BY_KIND.get(transition.kind)
        if key is None:
            return
        targets = setting(self._entry, key, []) or []
        await self._trigger_automations(
            [target for target in targets if target.startswith(AUTOMATION_PREFIX)]
        )
        await self._run_scripts(
            [target for target in targets if target.startswith(SCRIPT_PREFIX)],
            payload,
        )

    async def _trigger_automations(self, entity_ids: list[str]) -> None:
        """Start the automations hooked to this kind of change.

        The conditions written in the automation are honoured rather than
        skipped: an automation that says "only at night" means it, and being
        started from here is not a reason to ignore what it says.

        Args:
            entity_ids: the automations to trigger.
        """
        if not entity_ids:
            return
        await self._hass.services.async_call(
            "automation",
            "trigger",
            {"entity_id": entity_ids, "skip_condition": False},
            blocking=False,
        )

    async def _run_scripts(self, entity_ids: list[str], payload: dict) -> None:
        """Start the scripts hooked to this kind of change, with what changed.

        Args:
            entity_ids: the scripts to run.
            payload: the variables the scripts receive.
        """
        if not entity_ids:
            return
        await self._hass.services.async_call(
            "script",
            "turn_on",
            {"entity_id": entity_ids, "variables": payload},
            blocking=False,
        )
