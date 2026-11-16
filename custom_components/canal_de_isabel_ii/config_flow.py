"""Config flow for Canal de Isabel II integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import CanalIsabelIIAPI
from homeassistant.util import dt as dt_util

from .const import CONF_JSESSIONID, CONF_SESSION_SET_AT, DOMAIN, SESSION_EXPIRED, SESSION_OK

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JSESSIONID): str,
    }
)

async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    api = CanalIsabelIIAPI(data[CONF_JSESSIONID])

    # We run this in an executor because requests is blocking
    state, detail = await hass.async_add_executor_job(api.probe)
    if state == SESSION_EXPIRED:
        raise InvalidAuth
    if state != SESSION_OK:
        _LOGGER.warning("Could not check the session with the portal: %s", detail)
        raise CannotConnect

    return {"title": "Canal de Isabel II"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Canal de Isabel II."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_JSESSIONID: user_input[CONF_JSESSIONID]})
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data={**user_input, CONF_SESSION_SET_AT: dt_util.utcnow().isoformat()},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> FlowResult:
        """Handle re-authentication with Canal de Isabel II."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Confirm reauthentication."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate the new cookie
                await validate_input(self.hass, user_input)
                
                # Update the existing entry
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={
                        **self.entry.data,
                        **user_input,
                        CONF_SESSION_SET_AT: dt_util.utcnow().isoformat(),
                    },
                )
                
                # Reload the entry to apply changes
                await self.hass.config_entries.async_reload(self.entry.entry_id)
                
                return self.async_abort(reason="reauth_successful")
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"account": "Canal de Isabel II"},
        )


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CannotConnect(HomeAssistantError):
    """Error to indicate the portal could not be reached or answered oddly."""
