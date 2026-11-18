from datetime import date

from engine import Biller, Duty, Engine, Module, Person
from engine.setup import build_setup, describe_schedule

TODAY = date(2026, 11, 18)


def rows(setup, kind):
    return next(s for s in setup["sections"] if s["kind"] == kind)["items"]


def make():
    e = Engine()
    e.add_person(Person("a", "Alex", notify="notify.mobile_a"))
    e.add_person(Person("b", "Basil"))  # no notify service yet
    e.add_module(Module("home", {"en": "Home"}, owners=["a"]))
    e.add_module(Module("lawn", {"en": "Lawn"}, owners=[]))  # no owner, no duties
    e.add_duty(
        Duty(id="filters", module="home", title={"en": "Change filters"},
             schedule={"type": "after_completion", "every": "3m", "first_due": "2026-12-01"}),
        TODAY,
    )
    return e


def test_sections_are_grouped_in_a_fixed_order():
    setup = build_setup(make())
    assert [s["kind"] for s in setup["sections"]] == ["people", "modules", "duties", "billers"]


def test_people_without_notify_need_setup():
    people = rows(build_setup(make()), "people")
    assert {p["id"]: p["issues"] for p in people} == {"a": [], "b": ["no_notify"]}


def test_modules_flag_missing_owner_and_empty():
    modules = {m["id"]: m for m in rows(build_setup(make()), "modules")}
    assert modules["home"]["issues"] == []
    assert modules["lawn"]["issues"] == ["no_owners", "no_duties"]
    assert modules["home"]["detail"] == "1 item(s) · Owners: Alex"


def test_duty_row_describes_schedule_and_module():
    (duty,) = rows(build_setup(make()), "duties")
    assert duty["title"] == "Change filters"
    assert duty["detail"] == "Home · 3m after it was last done"
    assert duty["issues"] == []


def test_duty_with_no_owner_is_flagged():
    e = make()
    e.add_duty(
        Duty(id="mow", module="lawn", title={"en": "Mow"},
             schedule={"type": "interval", "every": "1w", "first_due": "2026-11-20"}),
        TODAY,
    )
    duties = {d["id"]: d for d in rows(build_setup(e), "duties")}
    assert duties["mow"]["issues"] == ["no_owner"]
    assert duties["filters"]["issues"] == []


def test_biller_duties_are_listed_under_billers_not_duties():
    e = make()
    e.add_biller(Biller("duke", "Duke Energy", module="home"), TODAY)
    setup = build_setup(e)
    assert [d["id"] for d in rows(setup, "duties")] == ["filters"]
    (biller,) = rows(setup, "billers")
    assert biller["title"] == "Duke Energy" and biller["detail"] == "Bill · Home"
    assert biller["issues"] == []


def test_biller_problems():
    e = make()
    e.add_biller(Biller("gas", "Gas Co", module="lawn"), TODAY)  # module has no owner
    e.add_biller(Biller("rent", "Zillow", kind="income", module="home"), TODAY)
    billers = {b["id"]: b["issues"] for b in rows(build_setup(e), "billers")}
    assert billers == {"gas": ["no_owner"], "rent": ["income_completes_nothing"]}


def test_todo_count_counts_rows_not_issues():
    # b (no notify) + lawn (2 issues, one row) = 2 rows
    assert build_setup(make())["todo_count"] == 2


def test_describe_schedule_kinds():
    assert describe_schedule({"type": "interval", "every": "1w"}) == "Every 1w"
    assert describe_schedule({"type": "day_of_month", "days": [1, 15]}) == "Day 1, 15 of each month"
    assert describe_schedule({"type": "yearly_window", "opens": "09-01", "due": "11-30"}) == "Yearly, 09-01 to 11-30"
    assert describe_schedule({"type": "signal"}) == "When a machine signals it"
    assert describe_schedule({}) == "No schedule"
