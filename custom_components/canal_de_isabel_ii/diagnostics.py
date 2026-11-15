"""Diagnostics for Canal de Isabel II: the recorded session lifetimes."""
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, KEEP_ALIVE_INTERVAL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return the session history. Never includes the session cookie."""
    tracker = hass.data[DOMAIN][entry.entry_id]["tracker"]
    return {
        "keep_alive_interval_minutes": KEEP_ALIVE_INTERVAL.total_seconds() / 60,
        "sessions": tracker.records,
    }
