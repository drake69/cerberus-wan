"""Configuration and options dialogs for Cerberus WAN."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from . import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DEFAULT_DISCONNECTED_LABEL,
    DEFAULT_UNKNOWN_LABEL,
    DOMAIN,
)
from .assembly import detect_network, monitor_settings
from .domain import Asn, ProviderTable

CONF_PROVIDER_TABLE = "provider_table"


def describe_detection(address: str | None, asn: Asn | None) -> str:
    """Render the detected line for the dialog description, as markdown.

    Args:
        address: the public address, or None.
        asn: the announcing network, or None.

    Returns:
        A short summary of what was detected, with a link that names the
        network for whoever has to decide what to call it.
    """
    if asn is None:
        return "nothing (fill the table by hand, or reopen this dialog later)"
    return f"AS{asn} ([who is this?]({asn.directory_url})), public address {address}"


def build_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the form schema shared by the setup and the options dialogs.

    Args:
        defaults: values to prefill the form with.

    Returns:
        The voluptuous schema for the form.
    """
    return vol.Schema(
        {
            vol.Optional(
                CONF_PROVIDER_TABLE, default=defaults.get(CONF_PROVIDER_TABLE, "")
            ): str,
            vol.Optional(
                CONF_DISCONNECTED_LABEL,
                default=defaults.get(
                    CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
                ),
            ): str,
            vol.Optional(
                CONF_UNKNOWN_LABEL,
                default=defaults.get(CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL),
            ): str,
        }
    )


def to_entry_payload(user_input: dict[str, Any]) -> dict[str, Any]:
    """Convert submitted form values into what the entry stores.

    Args:
        user_input: the raw values coming back from the form.

    Returns:
        The payload with the provider text already parsed into a mapping.
    """
    table = ProviderTable.parse(user_input.get(CONF_PROVIDER_TABLE, ""))
    return {
        CONF_PROVIDERS: table.as_mapping(),
        CONF_DISCONNECTED_LABEL: user_input.get(
            CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
        ),
        CONF_UNKNOWN_LABEL: user_input.get(CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL),
    }


class CerberusWanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup dialog."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Detect the network in use, ask for its name, and create the entry.

        Args:
            user_input: submitted values, or None when the form opens.

        Returns:
            The form to display, or the created entry.
        """
        if user_input is not None:
            return self.async_create_entry(
                title="Cerberus WAN", data=to_entry_payload(user_input)
            )

        address, asn = await detect_network(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=build_schema(
                {CONF_PROVIDER_TABLE: ProviderTable().suggestion(asn)}
            ),
            description_placeholders={"detected": describe_detection(address, asn)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options dialog for an existing entry.

        Args:
            entry: the entry being reconfigured.

        Returns:
            The options flow handler.
        """
        return CerberusWanOptionsFlow()


class CerberusWanOptionsFlow(OptionsFlow):
    """Handle edits to the provider table after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the table, offering the network in use when it is unmapped.

        Args:
            user_input: submitted values, or None when the form opens.

        Returns:
            The form to display, or the updated options.
        """
        if user_input is not None:
            return self.async_create_entry(data=to_entry_payload(user_input))

        settings = monitor_settings(self.config_entry)
        address, asn = await detect_network(self.hass)
        return self.async_show_form(
            step_id="init",
            data_schema=build_schema(
                {
                    CONF_PROVIDER_TABLE: settings.table.suggestion(asn),
                    CONF_DISCONNECTED_LABEL: settings.disconnected_label,
                    CONF_UNKNOWN_LABEL: settings.unknown_label,
                }
            ),
            description_placeholders={"detected": describe_detection(address, asn)},
        )
