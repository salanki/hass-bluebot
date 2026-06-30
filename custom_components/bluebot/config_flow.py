"""Config, reauth and options flows for the Bluebot integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_FLOW_SCAN_INTERVAL,
    CONF_TOTALS_SCAN_INTERVAL,
    DEFAULT_FLOW_SCAN_INTERVAL,
    DEFAULT_TOTALS_SCAN_INTERVAL,
    DOMAIN,
    FLOW_SCAN_MAX,
    FLOW_SCAN_MIN,
    TOTALS_SCAN_MAX,
    TOTALS_SCAN_MIN,
)
from .pybluebot import (
    BluebotAuthError,
    BluebotClient,
    BluebotConnectionError,
    BluebotError,
)


async def _validate(hass, api_key: str) -> str:
    """Return the organization id for ``api_key`` or raise a client error."""
    session = async_get_clientsession(hass)
    client = BluebotClient(api_key, session)
    return await client.async_validate()


class BluebotConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                org_id = await _validate(self.hass, user_input[CONF_API_KEY])
            except BluebotAuthError:
                errors["base"] = "invalid_auth"
            except (BluebotConnectionError, BluebotError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(org_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Bluebot", data={CONF_API_KEY: user_input[CONF_API_KEY]}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                org_id = await _validate(self.hass, user_input[CONF_API_KEY])
            except BluebotAuthError:
                errors["base"] = "invalid_auth"
            except (BluebotConnectionError, BluebotError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(org_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return BluebotOptionsFlow()


class BluebotOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FLOW_SCAN_INTERVAL,
                    default=options.get(
                        CONF_FLOW_SCAN_INTERVAL,
                        int(DEFAULT_FLOW_SCAN_INTERVAL.total_seconds()),
                    ),
                ): vol.All(int, vol.Range(min=FLOW_SCAN_MIN, max=FLOW_SCAN_MAX)),
                vol.Optional(
                    CONF_TOTALS_SCAN_INTERVAL,
                    default=options.get(
                        CONF_TOTALS_SCAN_INTERVAL,
                        int(DEFAULT_TOTALS_SCAN_INTERVAL.total_seconds()),
                    ),
                ): vol.All(int, vol.Range(min=TOTALS_SCAN_MIN, max=TOTALS_SCAN_MAX)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
