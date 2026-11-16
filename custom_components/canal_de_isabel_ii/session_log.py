"""Record how long each portal session survives.

The portal gives no documented session lifetime, so we measure it: when a
session was handed to Home Assistant, every successful check, and the first
failure. The history is kept in .storage so it survives restarts and can be
compared across sessions (fixed duration, fixed clock time, or random).
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_RECORDS = 50
SAVE_DELAY = 30


def session_store(hass: HomeAssistant, entry_id: str) -> Store:
    """Return the store holding the session history of a config entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.sessions.{entry_id}")


def _local(iso: Optional[str]) -> str:
    if not iso:
        return "never"
    parsed = dt_util.parse_datetime(iso)
    if parsed is None:
        return iso
    return dt_util.as_local(parsed).strftime("%Y-%m-%d %H:%M:%S")


def _duration(start_iso: Optional[str], end_iso: Optional[str]) -> str:
    start = dt_util.parse_datetime(start_iso) if start_iso else None
    end = dt_util.parse_datetime(end_iso) if end_iso else None
    if start is None or end is None:
        return "unknown"
    minutes = int((end - start).total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


class SessionTracker:
    """Track the lifetime of the session currently configured in an entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str, set_at: str) -> None:
        self._store = session_store(hass, entry_id)
        self._set_at = set_at
        self._records: List[Dict[str, Any]] = []
        self._current: Dict[str, Any] = {}

    @property
    def records(self) -> List[Dict[str, Any]]:
        """All recorded sessions, oldest first."""
        return self._records

    async def async_load(self) -> None:
        """Load the history and select (or start) the record for this session."""
        data = await self._store.async_load() or {}
        self._records = data.get("sessions", [])
        for record in self._records:
            if record.get("set_at") == self._set_at:
                self._current = record
                return
        self._current = {
            "set_at": self._set_at,
            "last_ok": None,
            "ok_count": 0,
            "failed_at": None,
            "detail": None,
        }
        self._records.append(self._current)
        del self._records[:-MAX_RECORDS]

    def record_ok(self) -> None:
        """Note that the session was accepted by the portal just now."""
        if self._current.get("failed_at"):
            return
        self._current["last_ok"] = dt_util.utcnow().isoformat()
        self._current["ok_count"] += 1
        self._store.async_delay_save(self._data, SAVE_DELAY)

    async def async_record_failure(self, detail: Optional[str]) -> None:
        """Note the first time the portal rejected the session."""
        if self._current.get("failed_at"):
            return
        now: datetime = dt_util.utcnow()
        self._current["failed_at"] = now.isoformat()
        self._current["detail"] = detail
        _LOGGER.warning(
            "Canal de Isabel II session ended. Given to Home Assistant: %s. "
            "Last accepted: %s (alive at least %s, %s successful checks). "
            "Rejected: %s. Portal response: %s",
            _local(self._current["set_at"]),
            _local(self._current["last_ok"]),
            _duration(self._current["set_at"], self._current["last_ok"]),
            self._current["ok_count"],
            _local(self._current["failed_at"]),
            detail or "no detail",
        )
        await self._store.async_save(self._data())

    async def async_close(self) -> None:
        """Write anything pending now, so no delayed save outlives the entry."""
        await self._store.async_save(self._data())

    def _data(self) -> Dict[str, Any]:
        return {"sessions": self._records}
