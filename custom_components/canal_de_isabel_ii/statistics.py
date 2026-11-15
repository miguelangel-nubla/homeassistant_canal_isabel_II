"""Write hourly consumption into Home Assistant's long-term statistics.

The data is stored as an external statistic (canal_de_isabel_ii:consumption_
<contract>) rather than under an entity, so hours from the past can be written
at their real time and the Energy panel can use them directly.
"""
import logging
import re
from datetime import datetime
from typing import Dict

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DOMAIN
from .statistics_helpers import StatRow, merge_statistics

_LOGGER = logging.getLogger(__name__)


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

    last = await recorder.async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    last_rows = last.get(statistic_id) or []
    last_sum = last_rows[0].get("sum") if last_rows else None

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
    existing = [
        StatRow(
            start=_as_utc(row["start"]),
            state=row.get("state") or 0.0,
            sum=row.get("sum") or 0.0,
        )
        for row in stored.get(statistic_id) or []
    ]

    rows = merge_statistics(hourly, existing, last_sum)
    if not rows:
        return 0

    metadata = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"Canal de Isabel II {contract}",
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
    _LOGGER.debug("Wrote %s hourly statistics for %s", len(rows), statistic_id)
    return len(rows)
