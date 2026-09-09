"""Telling Home Assistant that the provider changed.

This is the Home Assistant side of the ChangeListener port. Two things happen
on a switchover, and they answer two different needs: an event is fired, for
whoever wants to write their own trigger and read what changed, and whatever
the entry hooked to the change is started, for whoever just wants an
automation to run and does not want to write a trigger at all.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import CONF_CHANGE_TARGETS, EVENT_PROVIDER_CHANGED, setting
from .domain import Observation

AUTOMATION_PREFIX = "automation."
SCRIPT_PREFIX = "script."


def describe(previous: Observation, current: Observation) -> dict:
    """Render a switchover as the data an automation can read.

    Args:
        previous: the reading before the change.
        current: the reading that is the change.

    Returns:
        What the event carries, and what a script receives as variables.
    """
    return {
        "previous_label": previous.label,
        "label": current.label,
        "public_address": current.address,
        "asn": current.asn.number if current.asn else None,
        "changed_at": current.moment.isoformat(),
    }


class HassAnnouncer:
    """Fires the event, and starts whatever was hooked to the change."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Bind the announcer to the entry whose settings it obeys.

        Args:
            hass: the running Home Assistant instance.
            entry: the config entry holding what to start.
        """
        self._hass = hass
        self._entry = entry

    async def provider_changed(
        self, previous: Observation, current: Observation
    ) -> None:
        """Announce a switchover.

        Args:
            previous: the reading before the change.
            current: the reading that is the change.
        """
        payload = describe(previous, current)
        payload["entry_id"] = self._entry.entry_id
        self._hass.bus.async_fire(EVENT_PROVIDER_CHANGED, payload)

        targets = setting(self._entry, CONF_CHANGE_TARGETS, []) or []
        await self._trigger_automations(
            [target for target in targets if target.startswith(AUTOMATION_PREFIX)]
        )
        await self._run_scripts(
            [target for target in targets if target.startswith(SCRIPT_PREFIX)],
            payload,
        )

    async def _trigger_automations(self, entity_ids: list[str]) -> None:
        """Start the automations hooked to the change.

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
        """Start the scripts hooked to the change, with what changed.

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
