"""The config and re-authentication flows: the account of the virtual office."""
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canal_de_isabel_ii.const import DOMAIN

ACCOUNT = {"document": " x1234567l ", "password": "secret", "profile": "particular"}


async def submit(hass, answers):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], answers)


async def test_the_account_is_stored_and_the_entry_waits_for_the_helper(hass):
    result = await submit(hass, ACCOUNT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data["document"] == "X1234567L"
    assert entry.data["password"] == "secret"
    assert entry.data["profile"] == "particular"
    assert entry.data["credentials_set_at"]
    # Loaded without any session: it asks the helper for one.
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_the_same_account_is_not_added_twice(hass):
    await submit(hass, ACCOUNT)
    result = await submit(hass, {**ACCOUNT, "document": "X1234567L"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_an_empty_document_is_asked_again(hass):
    result = await submit(hass, {**ACCOUNT, "document": "  "})
    assert result["errors"] == {"document": "document_required"}


async def test_reauth_keeps_the_rest_of_the_entry_data(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={**ACCOUNT, "document": "X1234567L", "credentials_set_at": "before", "history_imported": True},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass, data={"detail": "Usuario o contraseña incorrectos"})
    assert result["description_placeholders"]["reason"].endswith("«Usuario o contraseña incorrectos»")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ACCOUNT, "password": "new"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"
    assert entry.data["history_imported"] is True
    # Entering the credentials again tells the helper to try again.
    assert entry.data["credentials_set_at"] != "before"


async def test_an_entry_from_before_the_credentials_asks_for_them(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=1, data={"jsessionid": "old", "history_imported": True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]

    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], ACCOUNT)
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data["history_imported"] is True


async def test_the_account_can_be_changed_at_any_time(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="X1234567L",
        data={**ACCOUNT, "document": "X1234567L", "credentials_set_at": "before", "history_imported": True},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"document": "x1234567l", "password": "changed", "profile": "empresa"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "changed"
    assert entry.data["profile"] == "empresa"
    assert entry.data["history_imported"] is True
    # The helper is told to try again, whatever it had given up on.
    assert entry.data["credentials_set_at"] != "before"


async def test_an_account_cannot_be_changed_into_one_already_configured(hass):
    MockConfigEntry(domain=DOMAIN, version=2, unique_id="12345678Z", data={**ACCOUNT, "document": "12345678Z"}).add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id="X1234567L", data={**ACCOUNT, "document": "X1234567L"})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"document": "12345678z", "password": "secret", "profile": "particular"}
    )
    assert result["reason"] == "already_configured"
    assert entry.data["document"] == "X1234567L"
