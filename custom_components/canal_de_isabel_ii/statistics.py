"""Write hourly consumption into Home Assistant's long-term statistics.

The data is stored as an external statistic (canal_de_isabel_ii:consumption_
<contract>) rather than under an entity, so hours from the past can be written
at their real time and the Energy panel can use them directly.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_list_statistic_ids,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DOMAIN
from .statistics_helpers import StatRow, merge_statistics

_LOGGER = logging.getLogger(__name__)

# hass.data key: rows handed to the recorder in this run, per statistic id.
_PENDING = f"{DOMAIN}_written_statistics"
# hass.data key: statistics written anew in this run (see async_move_hours_back).
# What the recorder has of them may still be the old rows, so only the rows
# handed to it count.
_REWRITTEN = f"{DOMAIN}_rewritten_statistics"
# Where it is noted that the stored hours have been moved.
_MIGRATIONS_STORE = f"{DOMAIN}.migrations"
_HOURS_MOVED = "hours_moved_back"


def consumption_statistic_id(contract: str) -> str:
    """Return the external statistic id for a contract."""
    return f"{DOMAIN}:consumption_{re.sub(r'[^a-z0-9_]', '_', contract.lower())}"


def _as_utc(value) -> datetime:
    if isinstance(value, (int, float)):
        return dt_util.utc_from_timestamp(value)
    return dt_util.as_utc(value)


async def async_import_consumption(
    hass: HomeAssistant, contract: str, hourly: Dict[datetime, float]
) -> int:
    """Merge {hour start: liters} into the contract's statistic.

    Returns the number of rows written.
    """
    if not hourly:
        return 0
    statistic_id = consumption_statistic_id(contract)
    recorder = get_instance(hass)

    if statistic_id in hass.data.get(_REWRITTEN, set()):
        last, stored = {}, {}
    else:
        last = await recorder.async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id, True, {"sum"}
        )
        stored = await recorder.async_add_executor_job(
            statistics_during_period,
            hass,
            min(hourly),
            None,
            {statistic_id},
            "hour",
            None,
            {"state", "sum"},
        )
    last_rows = last.get(statistic_id) or []
    last_sum = last_rows[0].get("sum") if last_rows else None
    last_start = _as_utc(last_rows[0]["start"]) if last_rows else None

    by_start = {
        _as_utc(row["start"]): StatRow(
            start=_as_utc(row["start"]),
            state=row.get("state") or 0.0,
            sum=row.get("sum") or 0.0,
        )
        for row in stored.get(statistic_id) or []
    }

    # Statistics are written through the recorder's queue, so the rows of the
    # previous import may not be readable yet (it does not write at all until
    # Home Assistant has finished starting). Count them as stored, or the
    # sums would start again from zero.
    pending = hass.data.setdefault(_PENDING, {}).get(statistic_id, [])
    if pending:
        first = min(hourly)
        by_start.update({row.start: row for row in pending if row.start >= first})
        newest = pending[-1]
        if last_start is None or newest.start >= last_start:
            last_sum = newest.sum
    existing = [by_start[start] for start in sorted(by_start)]

    rows = merge_statistics(hourly, existing, last_sum)
    if not rows:
        return 0
    hass.data[_PENDING][statistic_id] = sorted(
        {**{row.start: row for row in pending}, **{row.start: row for row in rows}}.values(),
        key=lambda row: row.start,
    )

    _write(hass, statistic_id, f"Canal de Isabel II {contract}", rows)
    _LOGGER.debug("Wrote %s hourly statistics for %s", len(rows), statistic_id)
    return len(rows)


def _write(hass: HomeAssistant, statistic_id: str, name: str, rows) -> None:
    metadata = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_class=VolumeConverter.UNIT_CLASS,
        unit_of_measurement=UnitOfVolume.LITERS,
    )
    async_add_external_statistics(
        hass,
        metadata,
        [StatisticData(start=row.start, state=row.state, sum=row.sum) for row in rows],
    )


async def async_move_hours_back(hass: HomeAssistant) -> None:
    """Move the hours stored by versions up to 2026.11.9 one hour back. Once.

    Those versions took the portal's hour label for the start of the hour.
    It is the end (see csv_parser.HOUR_LABEL_IS_END), so every stored hour
    sits one hour late. Each statistic is read, cleared and written again an
    hour earlier, with the same liters and the same total.
    """
    store = Store(hass, 1, _MIGRATIONS_STORE)
    done = await store.async_load() or {}
    if done.get(_HOURS_MOVED):
        return
    recorder = get_instance(hass)
    listed = await async_list_statistic_ids(hass, statistic_type="sum")
    for statistic in listed:
        statistic_id = statistic["statistic_id"]
        if not statistic_id.startswith(f"{DOMAIN}:consumption_"):
            continue
        stored = await recorder.async_add_executor_job(
            statistics_during_period,
            hass,
            dt_util.utc_from_timestamp(0),
            None,
            {statistic_id},
            "hour",
            None,
            {"state"},
        )
        moved = {
            _as_utc(row["start"]) - timedelta(hours=1): row.get("state") or 0.0
            for row in stored.get(statistic_id) or []
        }
        if not moved:
            continue
        rows = merge_statistics(moved, [], None)
        # Both go through the recorder's queue, in this order.
        recorder.async_clear_statistics([statistic_id])
        _write(hass, statistic_id, statistic.get("name") or statistic_id, rows)
        hass.data.setdefault(_PENDING, {})[statistic_id] = rows
        hass.data.setdefault(_REWRITTEN, set()).add(statistic_id)
        _LOGGER.warning(
            "The %s hours of %s were stored one hour late by earlier versions "
            "and have been moved one hour back",
            len(rows),
            statistic_id,
        )
    await store.async_save({**done, _HOURS_MOVED: dt_util.utcnow().isoformat()})
