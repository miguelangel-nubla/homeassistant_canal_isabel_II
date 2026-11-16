"""The Canal de Isabel II integration.

The portal has no API and its login form runs a captcha, so the login is
done by the session helper, a browser that runs next to Home Assistant.
The integration never calls the helper. It keeps a list of the entries
that want a portal session, and the helper asks for that list every minute
(service session_request), logs in with the credentials it is given there,
and delivers the session (service set_session) or says why it could not
(service report_login).

A session is only wanted when data is about to be read, twice a day. It is
not kept alive in between.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, CanalIsabelIIAPI
from .const import (
    CONF_CREDENTIALS_SET_AT,
    CONF_DOCUMENT,
    CONF_HISTORY_IMPORTED,
    CONF_JSESSIONID,
    CONF_PASSWORD,
    CONF_PROFILE,
    CONF_SESSION_SET_AT,
    DEFAULT_PROFILE,
    DOMAIN,
    HELPER_DOCS_URL,
    HELPER_TIMEOUT,
    HELPER_WATCH_INTERVAL,
    HISTORY_DAYS,
    ISSUE_HELPER_MISSING,
    ISSUE_LOGIN,
    LOGIN_REFUSED,
    LOGIN_RESULTS,
    REFRESH_DAYS,
    REFRESH_INTERVAL,
    RETRY_INTERVAL,
    SERVICE_REPORT_LOGIN,
    SERVICE_SESSION_REQUEST,
    SERVICE_SET_SESSION,
    SESSION_EXPIRED,
    SESSION_OK,
)
from .csv_parser import hourly_totals
from .session_log import SessionTracker, session_store
from .statistics import async_import_consumption

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "number"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Kept in hass.data[DOMAIN]: when a helper last asked for work.
HELPER_SEEN = "helper_seen"

SESSION_REQUEST_SCHEMA = vol.Schema({vol.Optional("helper_url"): cv.string})
SET_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JSESSIONID): vol.All(cv.string, vol.Strip, vol.Length(min=1)),
        vol.Optional("entry_id"): cv.string,
    }
)
REPORT_LOGIN_SCHEMA = vol.Schema(
    {
        vol.Required("result"): vol.In(LOGIN_RESULTS),
        vol.Optional("entry_id"): cv.string,
        vol.Optional("detail"): cv.string,
        vol.Optional("retry_at"): cv.string,
        vol.Optional("helper_url"): cv.string,
    }
)


@dataclass
class Runtime:
    """What a loaded entry keeps while it runs."""

    coordinator: DataUpdateCoordinator
    tracker: Optional[SessionTracker] = None
    # Since when a portal session is wanted. None while there is no need.
    wanted_since: Optional[datetime] = None
    # The portal refused the credentials: wait for the person to enter them again.
    refused: bool = False
    # The settings of the leak check that differ from the defaults, by
    # contract: {contract: {"rest_liters": ..., "leak_hours": ...}}. They
    # belong to the number entities (number.py), which keep them.
    leak_settings: Dict[str, Dict[str, float]] = field(default_factory=dict)


def _runtime(hass: HomeAssistant, entry: ConfigEntry) -> Optional[Runtime]:
    """What a loaded entry keeps (entry.runtime_data). None while it is not loaded."""
    if entry.state is not ConfigEntryState.LOADED:
        return None
    return getattr(entry, "runtime_data", None)


def _login_issue_id(entry: ConfigEntry) -> str:
    return f"{ISSUE_LOGIN}_{entry.entry_id}"


def _pick_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    """The entry a helper's call is about."""
    entries = hass.config_entries.async_entries(DOMAIN)
    entry_id = call.data.get("entry_id")
    if entry_id:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_entry" if not entries else "several_entries",
        )
    return entries[0]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services the session helper works with."""
    hass.data.setdefault(DOMAIN, {})

    async def async_session_request(call: ServiceCall) -> ServiceResponse:
        """Tell the helper which entries want a session, with their credentials."""
        hass.data[DOMAIN][HELPER_SEEN] = dt_util.utcnow()
        ir.async_delete_issue(hass, DOMAIN, ISSUE_HELPER_MISSING)
        requests = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = _runtime(hass, entry)
            if runtime is None or runtime.wanted_since is None or runtime.refused:
                continue
            requests.append(
                {
                    "entry_id": entry.entry_id,
                    CONF_DOCUMENT: entry.data[CONF_DOCUMENT],
                    CONF_PASSWORD: entry.data[CONF_PASSWORD],
                    CONF_PROFILE: entry.data.get(CONF_PROFILE, DEFAULT_PROFILE),
                    CONF_CREDENTIALS_SET_AT: entry.data.get(CONF_CREDENTIALS_SET_AT, ""),
                }
            )
        return {"requests": requests}

    async def async_set_session(call: ServiceCall) -> None:
        """Take a portal session from the helper and read the data with it."""
        entry = _pick_entry(hass, call)
        runtime = _runtime(hass, entry)
        if runtime is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
        jsessionid = call.data[CONF_JSESSIONID]

        state, detail = await hass.async_add_executor_job(CanalIsabelIIAPI(jsessionid).probe)
        if state == SESSION_EXPIRED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="session_rejected"
            )
        if state != SESSION_OK:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="portal_unreachable",
                translation_placeholders={"detail": str(detail)},
            )
        if jsessionid != entry.data.get(CONF_JSESSIONID):
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_JSESSIONID: jsessionid,
                    CONF_SESSION_SET_AT: dt_util.utcnow().isoformat(),
                },
            )
            _LOGGER.debug("New portal session received from the session helper")
        runtime.wanted_since = None
        ir.async_delete_issue(hass, DOMAIN, _login_issue_id(entry))
        await runtime.coordinator.async_refresh()

    async def async_report_login(call: ServiceCall) -> None:
        """Hear from the helper that it could not log in, and tell the person."""
        entry = _pick_entry(hass, call)
        runtime = _runtime(hass, entry)
        if runtime is None or runtime.wanted_since is None:
            return  # no longer waiting for that login
        result = call.data["result"]
        detail = call.data.get("detail") or ""
        _LOGGER.warning(
            "The session helper could not log in to the portal (%s)%s",
            result,
            f": {detail}" if detail else "",
        )
        if result == LOGIN_REFUSED:
            # Wrong credentials, most likely: ask for them again.
            runtime.refused = True
            # What an earlier try reported no longer describes the situation.
            ir.async_delete_issue(hass, DOMAIN, _login_issue_id(entry))
            entry.async_start_reauth(hass, data={"detail": detail})
            return
        retry_at = dt_util.parse_datetime(call.data.get("retry_at") or "")
        url = call.data.get("helper_url") or ""
        ir.async_create_issue(
            hass,
            DOMAIN,
            _login_issue_id(entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            # With the address of the helper's browser, when the helper knows
            # it, the notice links to it.
            translation_key=f"login_{result}_link" if url else f"login_{result}",
            translation_placeholders={
                "retry_at": dt_util.as_local(retry_at).strftime("%H:%M") if retry_at else "?",
                "url": url,
            },
            learn_more_url=HELPER_DOCS_URL,
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SESSION_REQUEST,
        async_session_request,
        schema=SESSION_REQUEST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(
        hass, DOMAIN, SERVICE_SET_SESSION, async_set_session, schema=SET_SESSION_SCHEMA
    )
    async_register_admin_service(
        hass, DOMAIN, SERVICE_REPORT_LOGIN, async_report_login, schema=REPORT_LOGIN_SCHEMA
    )

    async def async_watch_helper(now: datetime) -> None:
        """Say so when a session is wanted and no helper is asking for work."""
        seen = hass.data[DOMAIN].get(HELPER_SEEN)
        if seen is not None and now - seen < HELPER_TIMEOUT:
            return
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = _runtime(hass, entry)
            if (
                runtime is not None
                and runtime.wanted_since is not None
                and now - runtime.wanted_since >= HELPER_TIMEOUT
            ):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    ISSUE_HELPER_MISSING,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=ISSUE_HELPER_MISSING,
                    learn_more_url=HELPER_DOCS_URL,
                )
                return

    stop_watching = async_track_time_interval(hass, async_watch_helper, HELPER_WATCH_INTERVAL)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: stop_watching())
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 held a session cookie and no credentials.

    The data is kept. Setting the entry up then asks for the credentials.
    """
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Canal de Isabel II from a config entry."""
    if not entry.data.get(CONF_DOCUMENT) or not entry.data.get(CONF_PASSWORD):
        # An entry from before the helper logged in by itself.
        raise ConfigEntryAuthFailed("The credentials of the virtual office are needed")

    def want_session() -> None:
        if runtime.wanted_since is None:
            runtime.wanted_since = dt_util.utcnow()
            _LOGGER.debug("A portal session is wanted; waiting for the session helper")

    async def async_update_data():
        """Read the portal, or ask for a session to read it with.

        Without a working session there is nothing to fetch: the data stays
        as it was and the fetch happens when the helper delivers a session.
        """
        jsessionid = entry.data.get(CONF_JSESSIONID)
        if not jsessionid or runtime.wanted_since is not None:
            want_session()
            return coordinator.data
        if CONF_SESSION_SET_AT not in entry.data:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_SESSION_SET_AT: dt_util.utcnow().isoformat()}
            )
        if runtime.tracker is None or runtime.tracker.set_at != entry.data[CONF_SESSION_SET_AT]:
            # A session delivered since the last fetch: its own record.
            if runtime.tracker is not None:
                await runtime.tracker.async_close()
            runtime.tracker = SessionTracker(hass, entry.entry_id, entry.data[CONF_SESSION_SET_AT])
            await runtime.tracker.async_load()

        # The first download asks for the whole history the portal keeps.
        first_import = not entry.data.get(CONF_HISTORY_IMPORTED)
        days = HISTORY_DAYS if first_import else REFRESH_DAYS
        api = CanalIsabelIIAPI(jsessionid)
        try:
            data = await hass.async_add_executor_job(api.get_consumption_data, days)
        except AuthError as err:
            # The session has ended, as every session does. Ask for another.
            await runtime.tracker.async_record_failure(str(err))
            want_session()
            return coordinator.data
        except Exception as err:
            coordinator.update_interval = RETRY_INTERVAL
            raise UpdateFailed(f"Error communicating with API: {err}")
        coordinator.update_interval = REFRESH_INTERVAL
        runtime.tracker.record_ok()

        imported = True
        for contract, hourly in hourly_totals(data.readings).items():
            try:
                await async_import_consumption(hass, contract, hourly)
            except Exception:  # pylint: disable=broad-except
                imported = False
                _LOGGER.exception("Could not import statistics for contract %s", contract)
        if first_import and imported and data.readings and data.range_applied:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_HISTORY_IMPORTED: True}
            )
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=REFRESH_INTERVAL,
    )
    runtime = Runtime(coordinator=coordinator)
    entry.runtime_data = runtime

    # A fetch that fails (the portal is down, the page could not be read)
    # does not stop the setup: it is tried again in a few minutes.
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        _LOGGER.warning(
            "No data from the portal yet, trying again in %s minutes: %s",
            int(RETRY_INTERVAL.total_seconds() // 60),
            coordinator.last_exception,
        )
    # Keeps the periodic fetch (and with it the statistics import) running
    # even when there are no entities listening, or all are disabled.
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: Runtime = entry.runtime_data
        if runtime.tracker is not None:
            await runtime.tracker.async_close()
        ir.async_delete_issue(hass, DOMAIN, _login_issue_id(entry))
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the session history when the entry is removed."""
    await session_store(hass, entry.entry_id).async_remove()


def runtime_summary(hass: HomeAssistant, entry: ConfigEntry) -> Dict[str, Any]:
    """The state of an entry, for the diagnostics. No secrets."""
    runtime = _runtime(hass, entry)
    seen = hass.data.get(DOMAIN, {}).get(HELPER_SEEN)
    return {
        "loaded": entry.state is ConfigEntryState.LOADED,
        "session_wanted_since": runtime.wanted_since.isoformat() if runtime and runtime.wanted_since else None,
        "login_refused": bool(runtime and runtime.refused),
        "helper_last_asked": seen.isoformat() if seen else None,
    }
