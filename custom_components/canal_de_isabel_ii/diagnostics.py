"""Diagnostics for Canal de Isabel II: the state of the entry and its past sessions."""
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import runtime_summary
from .const import DOMAIN
from .session_log import session_store


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return the state and the session history. Never the cookie or the credentials.

    The history comes from storage while the entry is not loaded.
    """
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is not None and runtime.tracker is not None:
        sessions = runtime.tracker.records  # includes what is not yet written
    else:
        sessions = (await session_store(hass, entry.entry_id).async_load() or {}).get("sessions", [])
    return {**runtime_summary(hass, entry), "sessions": sessions}
