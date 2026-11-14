from datetime import date, datetime

import pytest
from engine import Duty, Engine, Module, Person


def at(s):
    return datetime.fromisoformat(s + "T09:00:00")


def make_engine():
    e = Engine()
    e.add_person(Person("adm", "Admin", role="admin"))
    e.add_person(Person("a", "A"))
    e.add_person(Person("b", "B", language="ar"))
    e.add_person(Person("obs", "Obs", role="observer"))
    e.add_module(Module("home", {"en": "Home"}, owners=["a", "b"]))
    return e


def duty(**kw):
    base = dict(
        id="filters",
        module="home",
        title={"en": "Filters"},
        schedule={"type": "after_completion", "every": "3m", "first_due": "2026-12-01"},
        remind=["-3d", "0d"],
        escalate=[{"after": "2d", "notify": ["admin"]}],
    )
    base.update(kw)
    return Duty(**base)


def kinds(result):
    return [(n.kind, n.recipients) for n in result.notifications]


def test_lifecycle_reminder_overdue_escalation():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    assert e.state("filters", date(2026, 11, 14)) == "upcoming"
    assert not e.tick(at("2026-11-20")).notifications

    r = e.tick(at("2026-11-28"))  # due - 3d
    assert kinds(r) == [("reminder", ["a", "b"])]  # -3d reminder fires before the due day
    # a second tick the same day sends nothing new
    assert not e.tick(at("2026-11-28")).notifications

    r = e.tick(at("2026-12-01"))  # due day: 0d reminder
    assert ("reminder", ["a", "b"]) in kinds(r)

    r = e.tick(at("2026-12-02"))  # overdue
    assert ("overdue", ["a", "b", "adm"]) in kinds(r)
    assert any(ev.type == "overdue" for ev in r.events)
    assert not any(k == "escalation" for k, _ in kinds(r))

    r = e.tick(at("2026-12-03"))  # due + 2d
    assert ("escalation", ["adm"]) in kinds(r)
    assert not e.tick(at("2026-12-04")).notifications  # escalation fires once


def test_complete_advances_and_records_history():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    e.tick(at("2026-12-01"))
    r = e.complete("filters", "a", at("2026-12-05"), "button", "14x25")
    assert r.events[0].type == "completed"
    assert e.history[-1].by == "a" and e.history[-1].note == "14x25"
    assert e.occurrences["filters"].due == date(2027, 3, 5)
    assert e.state("filters", date(2026, 12, 6)) == "upcoming"


def test_complete_method_must_be_allowed():
    e = make_engine()
    e.add_duty(duty(done_by=["button"]), date(2026, 11, 14))
    with pytest.raises(ValueError):
        e.complete("filters", "a", at("2026-12-01"), "nfc")
    with pytest.raises(ValueError):
        e.complete("filters", "a", at("2026-12-01"), "auto")


def test_snooze_suppresses_then_resumes():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    e.tick(at("2026-12-01"))
    e.snooze("filters", date(2026, 12, 5), date(2026, 12, 2))
    assert e.state("filters", date(2026, 12, 3)) == "snoozed"
    assert not e.tick(at("2026-12-03")).notifications
    assert e.state("filters", date(2026, 12, 5)) == "overdue"
    with pytest.raises(ValueError):
        e.snooze("filters", date(2026, 12, 1), date(2026, 12, 2))


def test_skip_requires_reason():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    with pytest.raises(ValueError):
        e.skip("filters", "a", at("2026-12-01"), "  ")
    e.skip("filters", "a", at("2026-12-01"), "tenant moved out")
    assert e.history[-1].kind == "skipped"


def test_window_opens_notification_and_no_double_zero_offset():
    e = make_engine()
    e.add_duty(
        duty(
            id="hoa",
            schedule={"type": "yearly_window", "opens": "03-01", "due": "03-31"},
            remind=["-7d", "0d"],
            escalate=[],
        ),
        date(2027, 2, 1),
    )
    r = e.tick(at("2027-03-01"))
    assert [k for k, _ in kinds(r)] == ["opened"]
    r = e.tick(at("2027-03-24"))
    assert [k for k, _ in kinds(r)] == ["reminder"]


def test_open_early_when_soil_temp():
    e = make_engine()
    sched = {
        "type": "condition",
        "not_before": "02-15",
        "not_after": "04-15",
        "open_early_when": {"soil_temp_5day_avg_f": 50},
    }
    e.add_duty(duty(id="pre", schedule=sched, remind=[], escalate=[]), date(2027, 1, 10))
    assert e.occurrences["pre"].opens == date(2027, 2, 15)
    e.tick(at("2027-01-20"), {"soil_temp_5day_avg_f": 52})  # 26 days early: allowed
    assert e.occurrences["pre"].opens == date(2027, 1, 20)
    assert e.state("pre", date(2027, 1, 20)) == "due"


def test_open_early_too_soon_is_ignored():
    e = make_engine()
    sched = {"type": "condition", "not_before": "02-15", "not_after": "04-15",
             "open_early_when": {"t": 50}}
    e.add_duty(duty(id="pre", schedule=sched, remind=[], escalate=[]), date(2027, 1, 1))
    e.tick(at("2027-01-05"), {"t": 60})
    assert e.occurrences["pre"].opens == date(2027, 2, 15)


def test_when_gated_condition_opens_and_auto_skips():
    e = make_engine()
    sched = {"type": "condition", "when": {"freeze": 1}, "not_before": "10-01", "not_after": "11-30"}
    e.add_duty(duty(id="hose", schedule=sched, remind=[], escalate=[]), date(2026, 10, 5))
    assert e.occurrences["hose"].opens is None
    e.tick(at("2026-10-20"), {"freeze": 0})
    assert e.state("hose", date(2026, 10, 20)) == "upcoming"
    e.tick(at("2026-10-25"), {"freeze": 1})
    assert e.state("hose", date(2026, 10, 25)) == "due"

    e.add_duty(duty(id="never", schedule=sched, remind=[], escalate=[]), date(2026, 10, 5))
    r = e.tick(at("2026-12-01"), {"freeze": 0})
    assert any(ev.type == "skipped" and ev.detail == "window_closed" for ev in r.events)
    assert e.occurrences["never"].due == date(2027, 11, 30)


def test_season_defers_out_of_season_due():
    e = make_engine()
    e.add_duty(
        duty(id="mow", schedule={"type": "after_completion", "every": "7d"},
             season=[3, 4, 5, 6, 7, 8, 9, 10, 11], remind=[], escalate=[]),
        date(2026, 12, 1),
    )
    assert e.occurrences["mow"].due == date(2027, 3, 1)


def test_signal_opens_and_auto_completes_pair():
    e = make_engine()
    e.add_duty(
        duty(id="rent-check", schedule={"type": "day_of_month", "days": [1]},
             done_by=["button", "auto"], remind=[], escalate=[]),
        date(2026, 11, 20),
    )
    e.add_duty(
        duty(id="rent-in", schedule={"type": "signal", "completes": ["rent-check"]},
             remind=[], escalate=[]),
        date(2026, 11, 20),
    )
    assert "rent-in" not in e.occurrences
    r = e.signal("rent-in", at("2026-12-01"))
    assert e.history[-1].duty_id == "rent-check" and e.history[-1].method == "auto"
    assert e.occurrences["rent-check"].due == date(2027, 1, 1)
    assert e.occurrences["rent-in"].due == date(2026, 12, 1)
    assert r.events[0].type == "completed"
    # a duplicate signal does not create a second occurrence
    e.signal("rent-in", at("2026-12-01"))
    assert len(e.occurrences) == 2


def test_signal_on_non_signal_duty_fails():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    with pytest.raises(ValueError):
        e.signal("filters", at("2026-12-01"))


def test_not_mine_rotates_owner_and_notifies_admin():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    n = e.not_mine("filters", "a", date(2026, 12, 1))
    assert n.recipients == ["b", "adm"]
    assert e.duties["filters"].owners == ["b", "a"]


def test_disable_enable_and_update_keep_or_reset_occurrence():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    e.set_enabled("filters", False, date(2026, 11, 14))
    assert "filters" not in e.occurrences
    e.set_enabled("filters", True, date(2026, 11, 14))
    assert "filters" in e.occurrences
    occ = e.occurrences["filters"]
    e.update_duty(duty(how_to="new text"), date(2026, 11, 14))
    assert e.occurrences["filters"] is occ
    e.update_duty(duty(schedule={"type": "after_completion", "every": "1m",
                                 "first_due": "2026-12-20"}), date(2026, 11, 14))
    assert e.occurrences["filters"].due == date(2026, 12, 20)


def test_health_flags_ownerless_duty_and_unknown_module_rejected():
    e = make_engine()
    e.modules["empty"] = Module("empty")
    e.add_duty(duty(id="x", module="empty"), date(2026, 11, 14))
    assert e.health() == ["no_owner:x"]
    with pytest.raises(ValueError):
        e.add_duty(duty(id="y", module="ghost"), date(2026, 11, 14))


def test_round_trip_storage():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    e.tick(at("2026-12-02"))
    e.complete("filters", "a", at("2026-12-03"))
    clone = Engine.from_dict(e.to_dict())
    assert clone.to_dict() == e.to_dict()


def test_digest():
    e = make_engine()
    e.add_duty(duty(), date(2026, 11, 14))
    e.tick(at("2026-12-02"))
    assert e.digest(date(2026, 12, 2))["overdue"] == ["filters"]


def test_nfc_tags_lookup_and_uniqueness():
    e = make_engine()
    e.add_duty(duty(nfc_tags=["tag-1"]), date(2026, 11, 14))
    assert e.find_by_tag("tag-1").id == "filters"
    assert e.find_by_tag("nope") is None
    with pytest.raises(ValueError):
        e.add_duty(duty(id="other", nfc_tags=["tag-1"]), date(2026, 11, 14))
    e.add_duty(duty(id="third", nfc_tags=["tag-3"]), date(2026, 11, 14))
    with pytest.raises(ValueError):
        e.update_duty(duty(id="third", nfc_tags=["tag-1"]), date(2026, 11, 14))
    e.set_enabled("filters", False, date(2026, 11, 14))
    assert e.find_by_tag("tag-1") is None  # a disabled duty releases its tag
