from datetime import datetime, timedelta, timezone

from statistics_helpers import StatRow, merge_statistics

T0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def h(n):
    return T0 + timedelta(hours=n)


def series(start_hour, liters, base=0.0):
    """Build stored rows for consecutive hours."""
    rows, running = [], base
    for offset, value in enumerate(liters):
        running += value
        rows.append(StatRow(h(start_hour + offset), value, running))
    return rows


def bars(rows, previous_sum):
    """What the Energy panel would draw: sum[n] - sum[n-1]."""
    out = []
    for row in rows:
        out.append(row.sum - previous_sum)
        previous_sum = row.sum
    return out


def test_nothing_new_writes_nothing():
    assert merge_statistics({}, series(0, [1, 2]), 3.0) == []


def test_first_import_starts_from_zero():
    rows = merge_statistics({h(1): 20.0, h(0): 10.0}, [], None)
    assert rows == [StatRow(h(0), 10.0, 10.0), StatRow(h(1), 20.0, 30.0)]


def test_append_continues_from_the_last_sum():
    rows = merge_statistics({h(5): 4.0, h(6): 6.0}, [], 100.0)
    assert rows == [StatRow(h(5), 4.0, 104.0), StatRow(h(6), 6.0, 110.0)]


def test_same_data_twice_writes_nothing():
    stored = series(0, [10, 20, 30])
    new = {row.start: row.state for row in stored}
    assert merge_statistics(new, stored, 60.0) == []


def test_sliding_window_only_writes_the_new_tail():
    # Stored hours 0-4; the download covers hours 2-6. Hours 0-1 are outside
    # the query range, hours 2-4 are unchanged.
    stored = series(0, [10, 10, 10, 10, 10])
    new = {h(n): 10.0 for n in range(2, 7)}
    rows = merge_statistics(new, stored[2:], 50.0)
    assert rows == [StatRow(h(5), 10.0, 60.0), StatRow(h(6), 10.0, 70.0)]


def test_sliding_window_never_produces_a_negative_bar():
    stored = series(0, [10, 10, 10, 10, 10])
    new = {h(n): 7.0 for n in range(2, 7)}  # values revised by the portal
    rows = merge_statistics(new, stored[2:], 50.0)
    assert rows[0].start == h(2)
    assert all(bar >= 0 for bar in bars(rows, previous_sum=stored[1].sum))
    assert rows[-1].sum == 20.0 + 5 * 7.0


def test_corrected_value_shifts_every_later_sum():
    stored = series(0, [10, 10, 10])
    rows = merge_statistics({h(1): 15.0}, stored[1:], 30.0)
    assert rows == [StatRow(h(1), 15.0, 25.0), StatRow(h(2), 10.0, 35.0)]


def test_backfill_before_all_stored_data_keeps_later_bars():
    stored = series(10, [5, 5, 5])
    rows = merge_statistics({h(0): 3.0, h(1): 4.0}, stored, 15.0)
    assert [row.start for row in rows] == [h(0), h(1), h(10), h(11), h(12)]
    assert bars(rows, previous_sum=0.0) == [3.0, 4.0, 5.0, 5.0, 5.0]


def test_backfill_into_a_gap_keeps_earlier_sums_untouched():
    # Stored: hours 0-1 (sum 20), then hours 10-11. New data fills hours 4-5.
    late = series(10, [5, 5], base=20.0)
    rows = merge_statistics({h(4): 1.0, h(5): 2.0}, late, 30.0)
    assert rows == [
        StatRow(h(4), 1.0, 21.0),
        StatRow(h(5), 2.0, 23.0),
        StatRow(h(10), 5.0, 28.0),
        StatRow(h(11), 5.0, 33.0),
    ]
