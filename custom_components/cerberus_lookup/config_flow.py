"""Configuration and options dialogs for Cerberus Lookup."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from . import (
    CONF_DISCONNECTED_LABEL,
    CONF_PROVIDERS,
    CONF_UNKNOWN_LABEL,
    DEFAULT_DISCONNECTED_LABEL,
    DEFAULT_UNKNOWN_LABEL,
    DOMAIN,
)
from .dns_lookup import resolve_announcing_asn, resolve_public_address
from .provider_table import parse_provider_table, suggest_table

CONF_PROVIDER_TABLE = "provider_table"

# Shorter than the sensor timeout: this runs while the dialog is opening, and a
# slow lookup would look like a frozen form. Failing to detect is harmless, the
# form simply opens without a suggestion.
DETECTION_TIMEOUT = 2.0


async def detect_current_asn(hass: HomeAssistant) -> tuple[str | None, int | None]:
    """Resolve the address and the network in use, to prefill the form.

    Args:
        hass: the running Home Assistant instance.

    Returns:
        The public address and the announcing autonomous system number, either
        of which is None when it could not be determined.
    """
    address = await hass.async_add_executor_job(resolve_public_address, DETECTION_TIMEOUT)
    if address is None:
        return None, None
    asn = await hass.async_add_executor_job(
        resolve_announcing_asn, address, DETECTION_TIMEOUT
    )
    return address, asn


# Hurricane Electric renders an autonomous system number as the name of the
# organisation behind it. The link is offered to the person reading the dialog,
# never fetched by this integration: if the site disappears the only loss is a
# convenience, not a feature. This keeps the "no third party service" rule
# intact, which is about runtime dependencies and not about hyperlinks.
ASN_DIRECTORY_URL = "https://bgp.he.net/AS{asn}"


def describe_detection(address: str | None, asn: int | None) -> str:
    """Render the detected line for the dialog description, as markdown.

    Args:
        address: the public address, or None.
        asn: the announcing autonomous system number, or None.

    Returns:
        A short summary of what was detected, with a link that names the
        network for whoever has to decide what to call it.
    """
    if asn is None:
        return "nothing (fill the table by hand, or reopen this dialog later)"
    link = ASN_DIRECTORY_URL.format(asn=asn)
    return f"AS{asn} ([who is this?]({link})), public address {address}"


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
    return {
        CONF_PROVIDERS: parse_provider_table(user_input.get(CONF_PROVIDER_TABLE, "")),
        CONF_DISCONNECTED_LABEL: user_input.get(
            CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
        ),
        CONF_UNKNOWN_LABEL: user_input.get(CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL),
    }


class CerberusLookupConfigFlow(ConfigFlow, domain=DOMAIN):
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
                title="Cerberus Lookup", data=to_entry_payload(user_input)
            )

        address, asn = await detect_current_asn(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=build_schema({CONF_PROVIDER_TABLE: suggest_table({}, asn)}),
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
        return CerberusLookupOptionsFlow()


class CerberusLookupOptionsFlow(OptionsFlow):
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

        current = {**self.config_entry.data, **self.config_entry.options}
        address, asn = await detect_current_asn(self.hass)
        return self.async_show_form(
            step_id="init",
            data_schema=build_schema(
                {
                    CONF_PROVIDER_TABLE: suggest_table(
                        current.get(CONF_PROVIDERS, {}), asn
                    ),
                    CONF_DISCONNECTED_LABEL: current.get(
                        CONF_DISCONNECTED_LABEL, DEFAULT_DISCONNECTED_LABEL
                    ),
                    CONF_UNKNOWN_LABEL: current.get(
                        CONF_UNKNOWN_LABEL, DEFAULT_UNKNOWN_LABEL
                    ),
                }
            ),
            description_placeholders={"detected": describe_detection(address, asn)},
        )
