"""What the hourly readings of a contract say, for the entities.

Pure Python on purpose (no Home Assistant, no relative imports) so it can be
tested on its own.

The portal publishes each day with half a day to a day of delay, so nothing
here is about now. The figures describe the last day the portal has
published in full, and the leak check looks for a meter that never stops,
which is how a dripping cistern or a leak after the meter shows up.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

PORTAL_TZ = ZoneInfo("Europe/Madrid")

# A day has 24 hours, 23 when the clocks go forward. On the day they go back
# the portal publishes the repeated hour once, so it has 24 as well.
FULL_DAY_HOURS = 23

# A household uses no water at all for some hour of every day or two. This
# many published hours in a row with consumption in each of them is taken as
# a possible leak.
LEAK_HOURS = 48


@dataclass(frozen=True)
class Insights:
    """Figures drawn from the hourly readings of one contract."""

    # End of the newest hour published.
    data_until: Optional[datetime] = None
    # The last day published in full: its date, its total and its quietest hour.
    last_day: Optional[date] = None
    last_day_liters: Optional[float] = None
    last_day_minimum: Optional[float] = None
    # Published hours with consumption, counted back from the newest one
    # until an hour without any.
    hours_without_pause: int = 0
    # Start of the newest hour without consumption, if there is one.
    last_pause: Optional[datetime] = None
    # None while there are not enough hours to tell.
    possible_leak: Optional[bool] = None


def insights(hours: Dict[datetime, float]) -> Insights:
    """Summarise {start of the hour (aware): liters} for one contract."""
    if not hours:
        return Insights()
    newest_first = sorted(hours, reverse=True)

    days: Dict[date, list] = {}
    for start, liters in hours.items():
        days.setdefault(start.astimezone(PORTAL_TZ).date(), []).append(liters)
    full_days = [day for day, values in days.items() if len(values) >= FULL_DAY_HOURS]
    last_day = max(full_days) if full_days else None

    without_pause = 0
    last_pause = None
    for start in newest_first:
        if hours[start] <= 0:
            last_pause = start
            break
        without_pause += 1

    if without_pause >= LEAK_HOURS:
        possible_leak: Optional[bool] = True
    elif last_pause is not None or len(newest_first) >= LEAK_HOURS:
        possible_leak = False
    else:
        possible_leak = None  # fewer hours than it takes to tell, none of them at rest

    return Insights(
        data_until=newest_first[0] + timedelta(hours=1),
        last_day=last_day,
        last_day_liters=round(sum(days[last_day]), 2) if last_day else None,
        last_day_minimum=min(days[last_day]) if last_day else None,
        hours_without_pause=without_pause,
        last_pause=last_pause,
        possible_leak=possible_leak,
    )
