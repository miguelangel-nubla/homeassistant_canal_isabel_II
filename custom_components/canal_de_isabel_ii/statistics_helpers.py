"""Merge freshly downloaded hourly readings into stored statistics.

Pure Python on purpose (no Home Assistant, no relative imports) so it can be
tested on its own.

The Energy panel draws each hour as sum[n] - sum[n-1]. A running sum that
restarts or shrinks therefore shows up as a huge negative bar. Every import
has to continue the stored series instead of rebuilding it from zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

TOLERANCE = 1e-6


@dataclass(frozen=True)
class StatRow:
    """One hourly statistic: liters used in that hour and the running sum."""

    start: datetime
    state: float
    sum: float


def merge_statistics(
    new: Dict[datetime, float],
    existing: List[StatRow],
    last_sum: Optional[float],
) -> List[StatRow]:
    """Return the rows to write so the stored series stays continuous.

    new: {hour start: liters} just downloaded.
    existing: stored rows whose start is at or after the earliest hour in
        new (any order).
    last_sum: sum of the newest stored row overall, None if nothing is stored.

    The same call covers every case: first import, appending newer hours,
    re-downloading hours already stored, and filling in older hours. Stored
    rows before the earliest new hour are never touched. On a clash the new
    value wins. Rows that would be written unchanged are left out, so
    importing the same data twice writes nothing.
    """
    if not new:
        return []

    stored = sorted(existing, key=lambda row: row.start)
    if stored:
        # Sum reached just before the first stored row in range. Nothing is
        # stored between the earliest new hour and that row, so this is also
        # the sum to start from.
        running = stored[0].sum - stored[0].state
    else:
        running = last_sum or 0.0

    liters_by_hour: Dict[datetime, float] = {row.start: row.state for row in stored}
    liters_by_hour.update(new)
    stored_by_hour = {row.start: row for row in stored}

    result: List[StatRow] = []
    changed = False
    for start in sorted(liters_by_hour):
        liters = liters_by_hour[start]
        running += liters
        if not changed:
            old = stored_by_hour.get(start)
            if (
                old is not None
                and abs(old.state - liters) < TOLERANCE
                and abs(old.sum - running) < TOLERANCE
            ):
                continue
            changed = True
        result.append(StatRow(start=start, state=liters, sum=running))
    return result
