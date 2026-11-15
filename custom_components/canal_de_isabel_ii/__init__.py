"""The Canal de Isabel II integration."""
import logging
from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CanalIsabelIIAPI, AuthError
from .const import (
    CONF_JSESSIONID,
    CONF_SESSION_SET_AT,
    DOMAIN,
    KEEP_ALIVE_INTERVAL,
    SESSION_EXPIRED,
    SESSION_OK,
)
from .session_log import SessionTracker, session_store

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

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
        try:
            # Run blocking API call in executor
            data = await hass.async_add_executor_job(api.get_consumption_data)
        except AuthError as err:
            await tracker.async_record_failure(str(err))
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
        if data:
            tracker.record_ok()
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(hours=12),
    )

    await coordinator.async_config_entry_first_refresh()

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

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the session history when the entry is removed."""
    await session_store(hass, entry.entry_id).async_remove()
