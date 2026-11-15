"""Diagnostics for Canal de Isabel II: the recorded session lifetimes."""
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import KEEP_ALIVE_INTERVAL
from .session_log import session_store


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return the session history. Never includes the session cookie.

    Read from storage so it also works while the entry is waiting for a new
    session, which is exactly when the history is wanted.
    """
    data = await session_store(hass, entry.entry_id).async_load() or {}
    return {
        "keep_alive_interval_minutes": KEEP_ALIVE_INTERVAL.total_seconds() / 60,
        "sessions": data.get("sessions", []),
    }
