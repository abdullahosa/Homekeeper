from datetime import date

import pytest
from engine import schedule as sch


def d(s):
    return date.fromisoformat(s)


def test_durations_and_month_clamp():
    assert sch.add_duration(d("2026-01-31"), "1m") == d("2026-02-28")
    assert sch.add_duration(d("2026-11-14"), "3m") == d("2027-02-14")
    assert sch.add_duration(d("2026-11-14"), "-7d") == d("2026-11-07")
    assert sch.add_duration(d("2026-11-14"), "2w") == d("2026-11-28")
    with pytest.raises(ValueError):
        sch.parse_duration("soon")


def test_validate_rejects_bad_schedules():
    with pytest.raises(ValueError):
        sch.validate({"type": "nope"})
    with pytest.raises(ValueError):
        sch.validate({"type": "day_of_month", "days": [32]})
    with pytest.raises(ValueError):
        sch.validate({"type": "interval", "every": "x"})


def test_day_of_month_first_and_next_with_business_day():
    s = {"type": "day_of_month", "days": [1, 15], "next_business_day": True}
    # 2026-11-14 -> next is Sunday 15th -> Monday 16th
    assert sch.first_window(s, d("2026-11-14")) == (d("2026-11-16"), d("2026-11-16"))
    # after completing the 1st (Dec 1 2026 is Tuesday) next is Dec 15 (Tuesday)
    assert sch.next_window(s, d("2026-12-01"), d("2026-12-01"))[1] == d("2026-12-15")


def test_day_of_month_late_completion_skips_missed_candidate():
    s = {"type": "day_of_month", "days": [1, 15]}
    assert sch.next_window(s, d("2026-12-01"), d("2026-12-16"))[1] == d("2027-01-01")
    assert sch.next_window(s, d("2026-12-01"), d("2026-12-05"))[1] == d("2026-12-15")


def test_interval_keeps_anchor_and_skips_past():
    s = {"type": "interval", "every": "3m", "anchor": "2026-01-15"}
    assert sch.first_window(s, d("2026-11-14"))[1] == d("2027-01-15")
    assert sch.next_window(s, d("2026-04-15"), d("2026-04-20"))[1] == d("2026-07-15")
    # very late: lands on the first anchor-aligned date after completion
    assert sch.next_window(s, d("2026-04-15"), d("2026-10-01"))[1] == d("2026-10-15")


def test_after_completion():
    s = {"type": "after_completion", "every": "3m"}
    assert sch.next_window(s, d("2026-02-01"), d("2026-03-10"))[1] == d("2026-06-10")
    assert sch.first_window(s, d("2026-11-14"))[1] == d("2027-02-14")
    s2 = {**s, "first_due": "2026-12-01"}
    assert sch.first_window(s2, d("2026-11-14"))[1] == d("2026-12-01")


def test_yearly_window_first_and_next():
    s = {"type": "yearly_window", "opens": "09-15", "due": "10-15"}
    assert sch.first_window(s, d("2026-11-14")) == (d("2027-09-15"), d("2027-10-15"))
    assert sch.first_window(s, d("2026-10-01")) == (d("2026-09-15"), d("2026-10-15"))
    assert sch.next_window(s, d("2026-10-15"), d("2026-10-02")) == (d("2027-09-15"), d("2027-10-15"))


def test_yearly_window_crossing_new_year():
    s = {"type": "yearly_window", "opens": "12-01", "due": "01-15"}
    assert sch.first_window(s, d("2026-12-20")) == (d("2026-12-01"), d("2027-01-15"))


def test_condition_met_forms():
    assert sch.condition_met({"t": 50}, {"t": 50.0})
    assert not sch.condition_met({"t": 50}, {"t": 49.9})
    assert not sch.condition_met({"t": 50}, {})
    assert sch.condition_met({"t": {"lte": 32}}, {"t": 30})
    assert not sch.condition_met({}, {"t": 1})


def test_season_shift():
    w = (d("2026-12-05"), d("2026-12-05"))
    assert sch.shift_into_season(w, [3, 4, 5]) == (d("2027-03-01"), d("2027-03-01"))
    assert sch.shift_into_season(w, None) == w
    assert sch.shift_into_season((d("2026-04-02"),) * 2, [3, 4]) == (d("2026-04-02"),) * 2
