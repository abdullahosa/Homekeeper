from datetime import date

from engine import Biller, Duty, Engine, Module, Person
from engine.overview import build_overview

TODAY = date(2026, 12, 5)


def make():
    e = Engine()
    e.add_person(Person("a", "Alex", language="en"))
    e.add_person(Person("b", "Basil", language="ar", role="admin"))
    e.add_module(Module("home", {"en": "Home", "ar": "المنزل"}, owners=["a"]))
    e.add_module(Module("bills", {"en": "Bills"}, owners=["b"]))
    base = {"module": "home", "title": {"en": "T"}}
    for ident, due in (("late", "2026-12-01"), ("today", "2026-12-05"), ("soon", "2026-12-09"), ("far", "2027-03-01")):
        e.add_duty(
            Duty(id=ident, **{**base, "title": {"en": ident.title()}},
                 schedule={"type": "after_completion", "every": "3m", "first_due": due}),
            date(2026, 11, 1),
        )
    return e


def test_orders_overdue_first_and_hides_far_future():
    o = build_overview(make(), TODAY)
    assert [i["duty_id"] for i in o["items"]] == ["late", "today", "soon"]
    assert [i["state"] for i in o["items"]] == ["overdue", "due", "upcoming"]
    assert [i["days"] for i in o["items"]] == [-4, 0, 4]
    assert o["counts"] == {"overdue": 1, "due": 1}


def test_horizon_and_snoozed():
    e = make()
    assert [i["duty_id"] for i in build_overview(e, TODAY, 0)["items"]] == ["late", "today"]
    assert len(build_overview(e, TODAY, 365)["items"]) == 4
    e.snooze("late", date(2026, 12, 8), TODAY)
    o = build_overview(e, TODAY)
    assert o["items"][-1]["duty_id"] == "late" and o["items"][-1]["state"] == "snoozed"
    assert o["items"][-1]["snoozed_until"] == "2026-12-08"
    assert o["counts"]["overdue"] == 0


def test_people_modules_owners_and_amount():
    e = make()
    e.add_biller(Biller(id="duke", name="Duke Energy", module="bills", owners=["b"]), TODAY)
    e.apply_bill_state(
        "duke",
        {"status": "due", "due_date": "2026-12-10", "amount": 99.5, "arrived": "2026-12-01"},
        __import__("datetime").datetime(2026, 12, 5, 9),
    )
    o = build_overview(e, TODAY)
    bill = next(i for i in o["items"] if i["duty_id"] == "bill-duke")
    assert bill["amount"] == 99.5 and bill["owners"] == ["b"] and bill["biller"] == "duke"
    assert bill["module_title"] == {"en": "Bills"}
    assert {p["id"] for p in o["people"]} == {"a", "b"}
    assert o["modules"][0]["title"]["ar"] == "المنزل"
    assert next(i for i in o["items"] if i["duty_id"] == "late")["owners"] == ["a"]
