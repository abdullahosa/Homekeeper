from datetime import date, datetime

from engine import Biller, Duty, Engine, Module, Person


def at(s):
    return datetime.fromisoformat(s + "T09:00:00")


def make():
    e = Engine()
    e.add_person(Person("adm", "Admin", role="admin"))
    e.add_person(Person("a", "A"))
    e.add_module(Module("bills", {"en": "Bills"}, owners=["a"]))
    e.add_module(Module("rental", {"en": "Rental"}, owners=["a"]))
    e.add_biller(
        Biller(id="duke", name="Duke Energy", cadence_days=31, grace_days=7), date(2026, 11, 1)
    )
    return e


def state(status="due", due="2026-12-10", amount=120.5, arrived="2026-11-20", **kw):
    return {"status": status, "due_date": due, "amount": amount, "arrived": arrived,
            "paid": None, "paid_amount": None, "autopay": False, **kw}


def test_bill_state_opens_a_pay_duty_with_amount():
    e = make()
    assert "bill-duke" not in e.occurrences  # nothing until a bill posts
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    occ = e.occurrences["bill-duke"]
    assert occ.due == date(2026, 12, 10) and occ.meta["amount"] == 120.5
    r = e.tick(at("2026-11-21"))
    assert [n.kind for n in r.notifications] == ["opened"]  # bill arrived push
    assert e.biller_seen["duke"] == "2026-11-20"


def test_replayed_state_is_idempotent_and_updates_amount():
    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    e.tick(at("2026-11-21"))
    e.apply_bill_state("duke", state(amount=130.0), at("2026-11-22"))
    assert e.occurrences["bill-duke"].meta["amount"] == 130.0
    assert not e.tick(at("2026-11-22")).notifications  # no second "opened"


def test_paid_state_closes_it_automatically_and_never_reopens():
    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    r = e.apply_bill_state("duke", state("paid", paid="2026-12-01", paid_amount=120.5), at("2026-12-01"))
    assert "bill-duke" not in e.occurrences
    assert e.history[-1].method == "auto" and r.events[0].method == "auto"
    # BillBot republishes the old due state on restart: stays closed
    e.apply_bill_state("duke", state(), at("2026-12-02"))
    assert "bill-duke" not in e.occurrences


def test_new_bill_supersedes_an_unpaid_old_one():
    e = make()
    e.apply_bill_state("duke", state(due="2026-11-10"), at("2026-11-05"))
    e.apply_bill_state("duke", state(due="2026-12-10"), at("2026-11-21"))
    assert e.occurrences["bill-duke"].due == date(2026, 12, 10)
    assert e.history[-1].kind == "skipped" and e.history[-1].note == "superseded"


def test_overdue_bill_discovered_late_is_overdue_immediately():
    e = make()
    e.apply_bill_state("duke", state("overdue", due="2026-11-10"), at("2026-11-15"))
    assert e.state("bill-duke", date(2026, 11, 15)) == "overdue"


def test_autopay_closes_and_none_status_is_ignored():
    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    e.apply_bill_state("duke", state("autopay", autopay=True), at("2026-11-22"))
    assert "bill-duke" not in e.occurrences and e.history[-1].note == "autopay"
    e.apply_bill_state("duke", {"status": "none", "due_date": None}, at("2026-11-23"))
    assert "bill-duke" not in e.occurrences


def test_paid_for_a_different_due_date_does_not_close_this_bill():
    e = make()
    e.apply_bill_state("duke", state(due="2026-12-10"), at("2026-11-21"))
    e.apply_bill_state("duke", state("paid", due="2026-10-10"), at("2026-11-22"))
    assert "bill-duke" in e.occurrences


def test_unknown_or_disabled_biller_ignored():
    e = make()
    assert not e.apply_bill_state("ghost", state(), at("2026-11-21")).events
    e.billers["duke"].enabled = False
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    assert "bill-duke" not in e.occurrences


def test_income_completes_rent_check_only_when_payment_is_recent():
    e = make()
    e.add_biller(
        Biller(id="rent", name="Rent", kind="income", module="rental",
               completes=["rent-check"], cadence_days=15), date(2026, 11, 1))
    e.add_duty(
        Duty(id="rent-check", module="rental", title={"en": "Rent"},
             schedule={"type": "day_of_month", "days": [1, 15]}, done_by=["button", "auto"]),
        date(2026, 11, 20),
    )
    assert e.occurrences["rent-check"].due == date(2026, 12, 1)
    # a stale payment from mid-November must not close the December 1 occurrence
    e.apply_bill_state("rent", {"status": "paid", "paid": "2026-11-15", "due_date": "2026-11-15"}, at("2026-11-20"))
    assert e.occurrences["rent-check"].due == date(2026, 12, 1)
    # rent arriving on the 30th closes it early; the next check is the 15th
    e.apply_bill_state("rent", {"status": "paid", "paid": "2026-11-30", "due_date": "2026-11-30"}, at("2026-11-30"))
    assert e.occurrences["rent-check"].due == date(2026, 12, 15)
    assert e.history[-1].method == "auto"
    # replay of the same retained message does nothing
    e.apply_bill_state("rent", {"status": "paid", "paid": "2026-11-30", "due_date": "2026-11-30"}, at("2026-12-01"))
    assert e.occurrences["rent-check"].due == date(2026, 12, 15)


def test_biller_silent_health_check():
    e = make()
    assert e.health(date(2026, 11, 20)) == []
    assert e.health(date(2026, 12, 20)) == ["biller_silent:duke"]  # 49 days, over 31 + 7
    e.apply_bill_state("duke", state(arrived="2026-12-15"), at("2026-12-15"))
    assert e.health(date(2026, 12, 20)) == []


def test_biller_round_trip_and_validation():
    import pytest

    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    clone = Engine.from_dict(e.to_dict())
    assert clone.to_dict() == e.to_dict()
    assert clone.billers["duke"].name == "Duke Energy"
    assert clone.occurrences["bill-duke"].meta["amount"] == 120.5
    with pytest.raises(ValueError):
        Biller.from_dict({"id": "x", "name": "X", "kind": "gift"})
    with pytest.raises(ValueError):
        Biller.from_dict({"id": "x", "name": ""})


# ------------------------------------------------------------ login page + note
def test_bill_duty_points_to_its_login_page_and_password_note():
    e = make()
    e.add_biller(
        Biller(id="duke", name="Duke Energy", login_url="https://example.com/login",
               login_note="Bitwarden > Home Bills > Duke Energy"),
        date(2026, 11, 1),
    )
    duty = e.duties["bill-duke"]
    assert e.login_for(duty).id == "duke"
    assert e.login_lines(duty) == [
        "Log in: https://example.com/login",
        "Bitwarden > Home Bills > Duke Energy",
    ]


def test_income_biller_login_shows_on_the_duty_it_completes():
    e = make()
    e.add_duty(
        Duty(id="rent-check", module="rental", title={"en": "Confirm rent"},
             schedule={"type": "day_of_month", "days": [1, 15]}),
        date(2026, 11, 1),
    )
    e.add_biller(
        Biller(id="rent", name="Zelle Rent", kind="income", module="rental",
               completes=["rent-check"], login_url="https://bank.example/login"),
        date(2026, 11, 1),
    )
    assert e.login_lines(e.duties["rent-check"]) == ["Log in: https://bank.example/login"]


def test_no_login_lines_without_a_link_or_note():
    e = make()
    assert e.login_for(e.duties["bill-duke"]) is None
    assert e.login_lines(e.duties["bill-duke"]) == []


def test_only_web_links_are_accepted():
    import pytest

    for bad in ("javascript:alert(1)", "duke-energy.com", "https://", "ftp://x"):
        with pytest.raises(ValueError):
            Biller.from_dict({"id": "x", "name": "X", "login_url": bad})
    assert Biller.from_dict({"id": "x", "name": "X", "login_url": "HTTPS://x.com"}).login_url


def test_overview_carries_login_for_the_card():
    from engine.overview import build_overview

    e = make()
    e.add_biller(
        Biller(id="duke", name="Duke Energy", login_url="https://example.com/login", login_note="In Bitwarden"),
        date(2026, 11, 1),
    )
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    item = next(i for i in build_overview(e, date(2026, 11, 21))["items"] if i["duty_id"] == "bill-duke")
    assert item["login_url"] == "https://example.com/login" and item["login_note"] == "In Bitwarden"


def test_old_saved_billers_load_without_login_fields():
    b = Biller.from_dict({"id": "duke", "name": "Duke Energy", "kind": "bill"})
    assert b.login_url == "" and b.login_note == ""


# ------------------------------------------------------------ bills table rows
def _bills(e, today="2026-11-21"):
    from engine.overview import build_bills

    return {r["id"]: r for r in build_bills(e, date.fromisoformat(today))}


def test_bills_table_shows_open_bill_with_amount_and_mark_paid():
    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    row = _bills(e)["duke"]
    assert row["status"] == "due" and row["amount"] == 120.5
    assert row["date"] == "2026-12-10" and row["days"] == 19
    assert row["duty_id"] == "bill-duke" and row["owners"] == ["a"]


def test_bills_table_keeps_paid_bills_visible():
    e = make()
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    e.apply_bill_state("duke", state(status="paid", paid="2026-11-25"), at("2026-11-25"))
    row = _bills(e, "2026-11-25")["duke"]
    assert row["status"] == "paid" and row["amount"] == 120.5 and row["duty_id"] is None


def test_bills_table_late_bill_is_overdue_and_unknown_is_none():
    e = make()
    e.add_biller(Biller(id="gas", name="Gas Co"), date(2026, 11, 1))
    e.apply_bill_state("duke", state(due="2026-11-20"), at("2026-11-15"))
    rows = _bills(e, "2026-11-22")
    assert rows["duke"]["status"] == "overdue" and rows["duke"]["days"] == -2
    assert rows["gas"]["status"] == "none" and rows["gas"]["amount"] is None


def test_bills_table_sorts_urgent_first_and_income_last():
    from engine.overview import build_bills

    e = make()
    e.add_biller(Biller(id="gas", name="Gas Co"), date(2026, 11, 1))
    e.add_biller(Biller(id="rent", name="Zelle Rent", kind="income", module="rental"), date(2026, 11, 1))
    e.apply_bill_state("gas", state(status="paid", due="2026-11-10", paid="2026-11-09"), at("2026-11-21"))
    e.apply_bill_state("duke", state(), at("2026-11-21"))
    e.apply_bill_state("rent", {"status": "paid", "paid": "2026-11-12", "paid_amount": 1150.0}, at("2026-11-21"))
    rows = build_bills(e, date(2026, 11, 21))
    assert [r["id"] for r in rows] == ["duke", "gas", "rent"]
    rent = rows[-1]
    assert rent["status"] == "received" and rent["amount"] == 1150.0 and rent["date"] == "2026-11-12"


def test_bills_table_carries_display_fields_and_arabic_pay_title():
    e = make()
    e.add_biller(
        Biller(id="duke", name="Duke Energy", name_ar="الكهرباء", icon="mdi:flash",
               login_url="https://example.com/login"),
        date(2026, 11, 1),
    )
    row = _bills(e)["duke"]
    assert (row["name_ar"], row["icon"], row["login_url"]) == ("الكهرباء", "mdi:flash", "https://example.com/login")
    assert e.duties["bill-duke"].title["ar"] == "سداد فاتورة الكهرباء"


def test_bill_states_survive_save_and_load():
    e = make()
    e.apply_bill_state("duke", state(status="paid", paid="2026-11-25"), at("2026-11-25"))
    again = Engine.from_dict(e.to_dict())
    assert again.bill_states["duke"]["status"] == "paid"
