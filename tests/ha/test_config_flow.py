"""The config and reauth flows, with the portal client replaced."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canal_de_isabel_ii.const import (
    DOMAIN,
    SESSION_ERROR,
    SESSION_EXPIRED,
    SESSION_OK,
)

ANSWERS = {
    "good": (SESSION_OK, None),
    "dead": (SESSION_EXPIRED, "HTTP 302 -> /c/portal/login"),
    "down": (SESSION_ERROR, "HTTP 503"),
}


class FakeClient:
    def __init__(self, jsessionid):
        self.jsessionid = jsessionid

    def probe(self):
        return ANSWERS[self.jsessionid]


def portal():
    return patch("custom_components.canal_de_isabel_ii.config_flow.CanalIsabelIIAPI", FakeClient)


async def submit(hass, cookie):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"jsessionid": cookie})


async def test_a_dead_session_and_an_unreachable_portal_are_told_apart(hass):
    with portal():
        assert (await submit(hass, "dead"))["errors"] == {"base": "invalid_auth"}
        assert (await submit(hass, "down"))["errors"] == {"base": "cannot_connect"}


async def test_the_same_session_is_not_added_twice(hass):
    MockConfigEntry(domain=DOMAIN, data={"jsessionid": "good"}).add_to_hass(hass)
    with portal():
        result = await submit(hass, "good")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_keeps_the_rest_of_the_entry_data(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"jsessionid": "old", "history_imported": True}
    )
    entry.add_to_hass(hass)
    with portal(), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"jsessionid": "good"}
        )
    assert result["reason"] == "reauth_successful"
    assert entry.data["jsessionid"] == "good"
    assert entry.data["history_imported"] is True
