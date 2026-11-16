"""Config flow for Canal de Isabel II: the account of the virtual office.

The credentials cannot be checked here. Only the session helper can log
in, and it does so once the entry exists. If the portal refuses them, the
helper says so and the re-authentication step asks for them again.
"""
from typing import Any, Dict, Mapping, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .const import (
    BASE_URL,
    CONF_CREDENTIALS_SET_AT,
    CONF_DOCUMENT,
    CONF_PASSWORD,
    CONF_PROFILE,
    DEFAULT_NAME,
    DEFAULT_PROFILE,
    DOMAIN,
    PROFILES,
)


def _schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DOCUMENT, default=defaults.get(CONF_DOCUMENT, vol.UNDEFINED)): TextSelector(),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_PROFILE, default=defaults.get(CONF_PROFILE, DEFAULT_PROFILE)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=PROFILES, mode=SelectSelectorMode.DROPDOWN, translation_key=CONF_PROFILE
                )
            ),
        }
    )


def _credentials(user_input: Dict[str, Any]) -> Dict[str, Any]:
    return {
        CONF_DOCUMENT: user_input[CONF_DOCUMENT].strip().upper(),
        CONF_PASSWORD: user_input[CONF_PASSWORD],
        CONF_PROFILE: user_input[CONF_PROFILE],
        CONF_CREDENTIALS_SET_AT: dt_util.utcnow().isoformat(),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Canal de Isabel II."""

    VERSION = 2

    def __init__(self) -> None:
        self._refusal = ""

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Ask for the account of the virtual office."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            data = _credentials(user_input)
            if not data[CONF_DOCUMENT]:
                errors[CONF_DOCUMENT] = "document_required"
            else:
                await self.async_set_unique_id(data[CONF_DOCUMENT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
            description_placeholders={"portal_url": f"{BASE_URL}/"},
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Change the account at any time, from the entry's menu.

        Re-authentication only comes up when the portal has refused a login.
        This is for the person who changed the password at the portal, or
        picked the wrong profile, and does not want to wait for that.
        """
        entry = self._get_reconfigure_entry()
        errors: Dict[str, str] = {}
        if user_input is not None:
            data = _credentials(user_input)
            if not data[CONF_DOCUMENT]:
                errors[CONF_DOCUMENT] = "document_required"
            else:
                await self.async_set_unique_id(data[CONF_DOCUMENT])
                for other in self._async_current_entries():
                    if other.entry_id != entry.entry_id and other.unique_id == data[CONF_DOCUMENT]:
                        return self.async_abort(reason="already_configured")
                # Everything else in the entry stays, the history included.
                return self.async_update_reload_and_abort(
                    entry, unique_id=data[CONF_DOCUMENT], data_updates=data
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or entry.data),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The portal refused the credentials, or the entry never had any."""
        # The helper passes on what the portal said when it refused the login.
        self._refusal = str(entry_data.get("detail") or "")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> ConfigFlowResult:
        """Ask for the credentials again."""
        entry = self._get_reauth_entry()
        errors: Dict[str, str] = {}
        if user_input is not None:
            data = _credentials(user_input)
            if not data[CONF_DOCUMENT]:
                errors[CONF_DOCUMENT] = "document_required"
            else:
                # Everything else in the entry stays, so the year of history
                # is not downloaded again.
                return self.async_update_reload_and_abort(
                    entry, unique_id=data[CONF_DOCUMENT], data_updates=data
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(user_input or entry.data),
            errors=errors,
            description_placeholders={
                # What the portal answered, when it refused a login.
                "reason": f"\n\nPortal: «{self._refusal}»" if self._refusal else "",
            },
        )
