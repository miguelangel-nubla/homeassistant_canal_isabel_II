"""The Canal de Isabel II integration."""
import logging
from homeassistant.helpers.event import async_track_time_interval

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CanalIsabelIIAPI, AuthError
from .const import (
    CONF_HISTORY_IMPORTED,
    CONF_JSESSIONID,
    CONF_SESSION_SET_AT,
    DOMAIN,
    HISTORY_DAYS,
    KEEP_ALIVE_INTERVAL,
    REFRESH_DAYS,
    REFRESH_INTERVAL,
    RETRY_INTERVAL,
    SERVICE_SET_SESSION,
    SESSION_EXPIRED,
    SESSION_OK,
)
from .csv_parser import hourly_totals
from .session_log import SessionTracker, session_store
from .statistics import async_import_consumption

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JSESSIONID): vol.All(cv.string, vol.Strip, vol.Length(min=1)),
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the service that lets another tool supply a session."""

    async def async_set_session(call: ServiceCall) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        entry_id = call.data.get("entry_id")
        if entry_id:
            entries = [entry for entry in entries if entry.entry_id == entry_id]
        if len(entries) != 1:
            raise ServiceValidationError(
                "No matching Canal de Isabel II entry"
                if not entries
                else "Several Canal de Isabel II entries exist: pass entry_id"
            )
        entry = entries[0]
        jsessionid = call.data[CONF_JSESSIONID]

        if jsessionid != entry.data.get(CONF_JSESSIONID):
            state, detail = await hass.async_add_executor_job(CanalIsabelIIAPI(jsessionid).probe)
            if state == SESSION_EXPIRED:
                raise ServiceValidationError("The portal did not accept this session")
            if state != SESSION_OK:
                raise ServiceValidationError(f"The session could not be checked with the portal: {detail}")
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_JSESSIONID: jsessionid,
                    CONF_SESSION_SET_AT: dt_util.utcnow().isoformat(),
                },
            )
            _LOGGER.info("New session received through the set_session service")
        elif entry.entry_id in hass.data.get(DOMAIN, {}):
            # Same session and the entry is running: nothing to do.
            return

        # A pending re-authentication request is now answered.
        for flow in hass.config_entries.flow.async_progress_by_handler(
            DOMAIN, match_context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}
        ):
            hass.config_entries.flow.async_abort(flow["flow_id"])
        # Reloading fetches and imports the data straight away.
        hass.config_entries.async_schedule_reload(entry.entry_id)

    async_register_admin_service(
        hass, DOMAIN, SERVICE_SET_SESSION, async_set_session, schema=SET_SESSION_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Canal de Isabel II from a config entry."""

    jsessionid = entry.data[CONF_JSESSIONID]
    api = CanalIsabelIIAPI(jsessionid)

    if CONF_SESSION_SET_AT not in entry.data:
        # Entry created before session tracking existed: the real start is unknown.
        _LOGGER.info("Session start time unknown; measuring its lifetime from now")
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SESSION_SET_AT: dt_util.utcnow().isoformat()}
        )
    tracker = SessionTracker(hass, entry.entry_id, entry.data[CONF_SESSION_SET_AT])
    await tracker.async_load()

    async def async_update_data():
        """Fetch data from API."""
        # The first download asks for the whole history the portal keeps.
        first_import = not entry.data.get(CONF_HISTORY_IMPORTED)
        days = HISTORY_DAYS if first_import else REFRESH_DAYS
        try:
            # Run blocking API call in executor
            data = await hass.async_add_executor_job(api.get_consumption_data, days)
        except AuthError as err:
            await tracker.async_record_failure(str(err))
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            coordinator.update_interval = RETRY_INTERVAL
            raise UpdateFailed(f"Error communicating with API: {err}")
        coordinator.update_interval = REFRESH_INTERVAL
        tracker.record_ok()

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

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as err:
        # The portal is down or the page could not be read. Carry on: the
        # session still gets its keep-alive and the fetch is tried again
        # later, instead of Home Assistant retrying the whole setup every
        # minute or so against the portal.
        _LOGGER.warning(
            "No data from the portal yet, trying again in %s minutes: %s",
            int(RETRY_INTERVAL.total_seconds() // 60),
            err,
        )
    # Keeps the periodic fetch (and with it the statistics import) running
    # even when there are no entities listening, or all are disabled.
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "tracker": tracker,
        "remove_keep_alive": None
    }

    async def run_keep_alive(now):
        """Keep the session alive and handle expiration."""
        state, detail = await hass.async_add_executor_job(api.probe)
        if state == SESSION_OK:
            tracker.record_ok()
        elif state == SESSION_EXPIRED:
            await tracker.async_record_failure(detail)
            # The refresh hits the login redirect and starts the re-authentication flow.
            await coordinator.async_request_refresh()
        else:
            _LOGGER.debug("Keep-alive could not reach the portal: %s", detail)

    remove_keep_alive = async_track_time_interval(
        hass, run_keep_alive, KEEP_ALIVE_INTERVAL
    )
    hass.data[DOMAIN][entry.entry_id]["remove_keep_alive"] = remove_keep_alive

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if data["remove_keep_alive"]:
            data["remove_keep_alive"]()
        await data["tracker"].async_close()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the session history when the entry is removed."""
    await session_store(hass, entry.entry_id).async_remove()
