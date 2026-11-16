"""What the entities say about the hourly readings."""
from datetime import date, datetime, timedelta, timezone

from insights import LEAK_HOURS, REST_LITERS, Insights, insights

# 00:00 in Madrid on 2026-06-01 (summer time, UTC+2).
MIDNIGHT = datetime(2026, 5, 31, 22, tzinfo=timezone.utc)


def hours(values, first=MIDNIGHT):
    return {first + timedelta(hours=offset): liters for offset, liters in enumerate(values)}


def test_no_readings_say_nothing():
    assert insights({}) == Insights()


def test_the_last_full_day_is_not_the_day_still_being_published():
    # A full day, then the first ten hours of the next one.
    result = insights(hours([5.0] * 8 + [0.0] * 4 + [20.0] * 12 + [1.0] * 10))
    assert result.last_day == date(2026, 6, 1)
    assert result.last_day_liters == 280.0
    assert result.last_day_minimum == 0.0
    assert result.data_until == MIDNIGHT + timedelta(hours=34)


def test_a_day_is_counted_in_madrid_time():
    # 24 hours from 22:00 UTC are one Madrid day, not parts of two UTC days.
    assert insights(hours([1.0] * 24)).last_day == date(2026, 6, 1)
    assert insights(hours([1.0] * 24, first=MIDNIGHT + timedelta(hours=2))).last_day is None


def test_the_short_day_of_the_spring_clock_change_is_a_full_day():
    # 2026-03-29 has 23 hours in Madrid: from 23:00 UTC the day before.
    start = datetime(2026, 3, 28, 23, tzinfo=timezone.utc)
    result = insights(hours([2.0] * 23, first=start))
    assert result.last_day == date(2026, 3, 29)
    assert result.last_day_liters == 46.0


def test_water_running_every_hour_for_two_days_is_a_possible_leak():
    result = insights(hours([0.0] + [3.0] * LEAK_HOURS))
    assert result.possible_leak is True
    assert result.hours_without_pause == LEAK_HOURS
    assert result.last_pause == MIDNIGHT
    assert result.last_day_minimum == 3.0  # the second day never rested


def test_one_hour_at_rest_is_enough_to_rule_a_leak_out():
    result = insights(hours([3.0] * 60 + [0.0] + [3.0] * (LEAK_HOURS - 1)))
    assert result.possible_leak is False
    assert result.hours_without_pause == LEAK_HOURS - 1


def test_too_few_hours_to_tell():
    assert insights(hours([3.0] * 10)).possible_leak is None
    assert insights(hours([0.0] + [3.0] * 10)).possible_leak is False


def test_the_trickle_a_meter_reports_at_rest_is_not_water_in_use():
    # A few hundredths of a liter in the quiet hours, as real meters report.
    day = [0.02] * 6 + [30.0] * 18
    result = insights(hours(day * 3))
    assert result.possible_leak is False
    assert result.hours_without_pause == 18
    assert result.last_day_minimum == 0.02
    # At the limit itself the water counts as running.
    assert insights(hours([REST_LITERS] * LEAK_HOURS)).possible_leak is True
