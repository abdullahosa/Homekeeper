"""Duties that follow a calendar, e.g. a city trash pickup calendar (ReCollect)."""

from datetime import date, datetime

import pytest
from engine import Duty, Engine, Module, Person
from engine import schedule as sch


def at(day, hour=9):
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00")


def make(**sched):
    e = Engine()
    e.add_person(Person("adm", "Admin", role="admin"))
    e.add_person(Person("a", "A"))
    e.add_module(Module("home", {"en": "Home"}, owners=["a"]))
    e.add_duty(
        Duty(id="bins", module="home", title={"en": "Put the bins out"},
             schedule={"type": "calendar", "calendar": "calendar.trash_pickup", "notify_at": "18:00", **sched}),
        date(2026, 11, 19),
    )
    return e


WEEK = [
    (date(2026, 11, 24), "Garbage, Recycling"),
    (date(2026, 12, 1), "Garbage"),
    (date(2026, 12, 8), "Garbage, Recycling"),
]


def test_calendar_schedule_validation():
    sch.validate({"type": "calendar", "calendar": "calendar.x", "lead": "1d", "notify_at": "18:00"})
    for bad in (
        {"type": "calendar"},
        {"type": "calendar", "calendar": "sensor.x"},
        {"type": "calendar", "calendar": "calendar.x", "lead": "3m"},
        {"type": "calendar", "calendar": "calendar.x", "notify_at": "6pm"},
        {"type": "calendar", "calendar": "calendar.x", "match": "Recycling"},
    ):
        with pytest.raises(ValueError):
            sch.validate(bad)


def test_nothing_until_the_calendar_reports_events():
    e = make()
    assert "bins" not in e.occurrences
    e.apply_calendar("bins", [], at("2026-11-19"))  # calendar not loaded yet
    assert "bins" not in e.occurrences


def test_opens_the_evening_before_with_what_is_collected():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-19"))
    occ = e.occurrences["bins"]
    assert occ.due == date(2026, 11, 23) and occ.opens == date(2026, 11, 23)
    assert occ.meta == {"event": "2026-11-24", "what": "Garbage + Recycling"}
    assert e.state("bins", date(2026, 11, 22)) == "upcoming"
    assert e.state("bins", date(2026, 11, 23)) == "due"
    assert e.state("bins", date(2026, 11, 24)) == "overdue"  # pickup morning, still not out


def test_lead_zero_means_the_same_day():
    e = make(lead="0d")
    e.apply_calendar("bins", WEEK, at("2026-11-19"))
    assert e.occurrences["bins"].due == date(2026, 11, 24)


def test_match_filters_and_separate_events_on_one_day_are_combined():
    events = [(date(2026, 11, 24), "Garbage"), (date(2026, 11, 24), "Recycling"),
              (date(2026, 12, 1), "Garbage")]
    e = make()
    e.apply_calendar("bins", events, at("2026-11-19"))
    assert e.occurrences["bins"].meta["what"] == "Garbage + Recycling"
    r = make(match=["recycling"])
    r.apply_calendar("bins", [(date(2026, 11, 24), "Garbage"), (date(2026, 12, 1), "Garbage, Recycling")],
                     at("2026-11-19"))
    assert r.occurrences["bins"].meta["event"] == "2026-12-01"


def test_done_moves_on_to_the_next_pickup_not_the_same_one():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-23"))
    e.complete("bins", "a", at("2026-11-23", 19), method="button")
    assert "bins" not in e.occurrences  # waits for the calendar again
    e.apply_calendar("bins", WEEK, at("2026-11-23", 19))  # same evening: Nov 24 already handled
    assert e.occurrences["bins"].meta["event"] == "2026-12-01"


def test_holiday_delay_moves_the_duty_and_tells_owners_when_close():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-19"))
    moved = [(date(2026, 11, 25), "Garbage, Recycling")] + WEEK[1:]  # Thanksgiving week: a day later
    quiet = e.apply_calendar("bins", moved, at("2026-11-19"))  # days ahead: just move it
    assert e.occurrences["bins"].due == date(2026, 11, 24) and quiet.notifications == []
    later = [(date(2026, 11, 26), "Garbage, Recycling")] + WEEK[1:]
    loud = e.apply_calendar("bins", later, at("2026-11-23", 9))  # bin night was tomorrow: tell them
    assert e.occurrences["bins"].due == date(2026, 11, 25)
    (note,) = loud.notifications
    assert note.kind == "moved" and note.detail == "2026-11-26" and note.recipients == ["a"]
    assert note.occurrence_id == e.occurrences["bins"].id


def test_reminders_restart_on_the_new_night():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-23"))
    first = e.tick(at("2026-11-23", 0))
    assert [n.kind for n in first.notifications] == ["opened"]
    moved = [(date(2026, 11, 25), "Garbage, Recycling")] + WEEK[1:]
    e.apply_calendar("bins", moved, at("2026-11-23", 12))
    assert e.tick(at("2026-11-23", 13)).notifications == []  # not tonight any more
    assert [n.kind for n in e.tick(at("2026-11-24", 0)).notifications] == ["opened"]


def test_missed_pickup_is_skipped_and_the_next_one_opens():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-23"))
    e.apply_calendar("bins", WEEK[1:], at("2026-11-25"))  # Nov 24 has gone from the calendar too
    assert e.history[-1].kind == "skipped" and e.history[-1].note == "event_passed"
    assert e.occurrences["bins"].meta["event"] == "2026-12-01"


def test_cancelled_pickup_drops_to_the_next_one():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-19"))
    e.apply_calendar("bins", WEEK[1:], at("2026-11-20"))
    assert e.occurrences["bins"].meta["event"] == "2026-12-01"
    assert not e.history  # moving is not a skip


def test_title_text_updates_without_resetting():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-23"))
    e.tick(at("2026-11-23", 0))
    occ = e.occurrences["bins"]
    e.apply_calendar("bins", [(date(2026, 11, 24), "Garbage, Recycling, Yard Waste")] + WEEK[1:], at("2026-11-23", 8))
    assert e.occurrences["bins"] is occ and occ.opened_notified
    assert occ.meta["what"] == "Garbage + Recycling + Yard waste"


def test_calendar_lines_and_overview_carry_what():
    from engine.overview import build_overview

    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-23"))
    assert e.calendar_lines(e.duties["bins"]) == ["Collecting: Garbage + Recycling on 2026-11-24"]
    item = next(i for i in build_overview(e, date(2026, 11, 23))["items"] if i["duty_id"] == "bins")
    assert item["what"] == "Garbage + Recycling" and item["event"] == "2026-11-24"


def test_survives_save_and_load():
    e = make()
    e.apply_calendar("bins", WEEK, at("2026-11-19"))
    again = Engine.from_dict(e.to_dict())
    assert again.occurrences["bins"].meta["event"] == "2026-11-24"


# What a real ReCollect city trash calendar says (area name changed).
RECOLLECT = [
    (date(2026, 11, 21), "Hhw collection - northside"),
    (date(2026, 11, 23), "Loose leaf - zone b - day 1"),
    (date(2026, 11, 25), "Loose leaf - zone b - day 3, yard waste - northside, bulky waste - northside, "
                         "recycling - northside, and garbage - northside"),
    (date(2026, 12, 2), "Loose leaf - zone b - day 7, hhw collection - northside, yard waste - northside, "
                        "and garbage - northside"),
    (date(2026, 12, 9), "Yard waste - northside, bulky waste - northside, recycling - northside, and garbage - northside"),
]


def test_recollect_calendar_with_match_garbage():
    e = make(match=["garbage"])
    e.apply_calendar("bins", RECOLLECT, at("2026-11-19"))
    occ = e.occurrences["bins"]
    assert occ.meta["event"] == "2026-11-25" and occ.due == date(2026, 11, 24)  # Tuesday evening
    assert occ.meta["what"] == "Garbage + Recycling + Yard waste + Bulky waste"
    e.complete("bins", "a", at("2026-11-24", 19), method="button")
    e.apply_calendar("bins", RECOLLECT, at("2026-11-24", 19))
    assert e.occurrences["bins"].meta["what"] == "Garbage + Yard waste"  # leaf and drop-off days left out


def test_without_match_a_drop_off_day_would_open_it():
    e = make()
    e.apply_calendar("bins", RECOLLECT, at("2026-11-19"))
    assert e.occurrences["bins"].meta["event"] == "2026-11-21"
    assert e.occurrences["bins"].meta["what"] == "Hhw collection"  # unknown words shown as written


def test_tidy_and_translate():
    from engine.collected import tidy, translate

    assert tidy(["Garbage", "Recycling"]) == ["Garbage", "Recycling"]
    assert tidy(["Trash & Yard Debris"]) == ["Garbage", "Yard waste"]
    assert tidy(["Street sweeping - zone 3"]) == ["Street sweeping"]
    assert translate("Garbage + Recycling + Bulky waste", "ar") == "النفايات + إعادة التدوير + الأغراض الكبيرة"
    assert translate("Garbage + Street sweeping", "en") == "Garbage + Street sweeping"
