"""The card's bills view in a real browser against a mock `hass`."""

from __future__ import annotations

import json

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card import CARD, DATA, HARNESS, SHOTS  # noqa: E402

BILLS = [
    {"id": "electric", "name": "Duke Energy", "name_ar": "الكهرباء", "icon": "mdi:flash", "kind": "bill",
     "module": "bills", "status": "due", "amount": 338.62, "date": "2026-11-20", "days": 1, "autopay": False,
     "duty_id": "bill-electric", "owners": ["alex", "dad"], "login_url": "https://example.com/duke",
     "login_note": "Vaultwarden > Home Bills > Duke Energy"},
    {"id": "water", "name": "City of Concord", "name_ar": "المياه", "icon": "mdi:water", "kind": "bill",
     "module": "bills", "status": "overdue", "amount": 87.65, "date": "2026-11-17", "days": -2, "autopay": False,
     "duty_id": "bill-water", "owners": ["sam"], "login_url": "", "login_note": ""},
    {"id": "internet", "name": "GFiber", "name_ar": "", "icon": "", "kind": "bill", "module": "bills",
     "status": "autopay", "amount": 100.0, "date": "2026-11-25", "days": 6, "autopay": True,
     "duty_id": None, "owners": ["sam"], "login_url": "https://example.com/gfiber", "login_note": ""},
    {"id": "gas", "name": "Enbridge Gas", "name_ar": "الغاز", "icon": "mdi:fire", "kind": "bill", "module": "bills",
     "status": "paid", "amount": 87.0, "date": "2026-11-16", "days": -3, "autopay": False,
     "duty_id": None, "owners": [], "login_url": "https://example.com/gas", "login_note": ""},
    {"id": "rent", "name": "Zelle Rent", "name_ar": "الإيجار", "icon": "", "kind": "income", "module": "rental",
     "status": "received", "amount": 1150.0, "date": "2026-11-12", "days": -7, "autopay": False,
     "duty_id": None, "owners": ["sam"], "login_url": "", "login_note": ""},
    {"id": "trash", "name": "Trash <b>Co</b>", "name_ar": "", "icon": "", "kind": "bill", "module": "bills",
     "status": "none", "amount": None, "date": None, "days": None, "autopay": False,
     "duty_id": None, "owners": [], "login_url": "javascript:alert(1)", "login_note": ""},
]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as err:  # pragma: no cover - browser missing
            pytest.skip(f"chromium unavailable: {err}")
        yield b
        b.close()


def _page(browser, cfg, width=420):
    page = browser.new_context(viewport={"width": width, "height": 1000}).new_page()
    page.set_content("<body style='margin:0;font-family:sans-serif'></body>")
    page.evaluate(f"window.DATA = {json.dumps({**DATA, 'bills': BILLS})}")
    page.add_script_tag(path=str(CARD))
    page.evaluate(HARNESS, cfg)
    page.wait_for_selector("homekeeper-card >> .bill")
    return page


def _row(page, name):
    return page.locator("homekeeper-card >> .bill", has_text=name)


def test_bills_view_rows_status_amounts_and_total(browser):
    page = _page(browser, {"mode": "bills"})
    card = page.inner_text("homekeeper-card >> .card")
    assert card.startswith("Bills")
    assert "$426.27 due" in card  # 338.62 + 87.65; autopay is not counted
    duke = _row(page, "Duke Energy").inner_text()
    assert "الكهرباء" in duke and "Due" in duke and "$338.62" in duke and "Nov 20 · Tomorrow" in duke
    assert "Alex, Dad" in duke and "Vaultwarden > Home Bills > Duke Energy" in duke
    water = _row(page, "City of Concord")
    assert "Overdue" in water.inner_text() and "2 days late" in water.inner_text()
    assert water.locator(".late").count() == 1
    gas = _row(page, "Enbridge Gas").inner_text()
    assert "Paid" in gas and "Due Nov 16" in gas
    rent = _row(page, "Zelle Rent").inner_text()
    assert "Received" in rent and "$1,150.00" in rent and "Received Nov 12" in rent
    assert page.locator("homekeeper-card >> .badge").inner_text() == "1 Overdue"
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "bills-view.png"), full_page=True)


def test_pay_link_while_due_log_in_link_once_paid(browser):
    page = _page(browser, {"mode": "bills"})
    pay = _row(page, "Duke Energy").locator(".login a")
    assert pay.inner_text() == "Pay ↗" and pay.get_attribute("href") == "https://example.com/duke"
    assert pay.get_attribute("rel") == "noopener noreferrer"
    assert _row(page, "Enbridge Gas").locator(".login a").inner_text() == "Log in ↗"
    assert _row(page, "City of Concord").locator(".login").count() == 0  # no link set
    assert _row(page, "Trash").locator("a").count() == 0  # never a javascript: link
    assert _row(page, "Trash").locator("b").count() == 0  # names are text, not HTML


def test_mark_paid_only_for_open_bills_and_asks_twice(browser):
    page = _page(browser, {"mode": "bills"})
    assert _row(page, "Enbridge Gas").locator("button").count() == 0
    assert _row(page, "GFiber").locator("button").count() == 0  # autopay, nothing open in Homekeeper
    button = _row(page, "Duke Energy").locator("button")
    assert button.inner_text() == "Mark paid"
    button.click()
    assert _row(page, "Duke Energy").locator("button").inner_text() == "Tap again to confirm"
    _row(page, "Duke Energy").locator("button").click()
    page.wait_for_function("window.calls.some(c => c[1] === 'complete')")
    call = next(c for c in page.evaluate("window.calls") if c[1] == "complete")
    assert call[0] == "homekeeper" and call[2]["duty_id"] == "bill-electric" and call[2]["method"] == "button"


def test_bills_view_in_arabic(browser):
    page = _page(browser, {"mode": "bills", "language": "ar"})
    assert page.locator("homekeeper-card >> .card").get_attribute("dir") == "rtl"
    duke = _row(page, "الكهرباء").inner_text()
    assert duke.splitlines()[0] == "الكهرباء" and "Duke Energy" in duke
    assert "مستحقة" in duke and "ادفع ↗" in duke and "تم الدفع" in duke
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "bills-view-ar.png"), full_page=True)


def test_module_filter_and_empty_state(browser):
    page = _page(browser, {"mode": "bills", "module": "rental"})
    assert page.locator("homekeeper-card >> .bill").count() == 1
    page.evaluate("window.DATA.bills = []; window.fire()")
    page.wait_for_selector("homekeeper-card >> .empty")
    assert "No billers yet" in page.inner_text("homekeeper-card >> .card")
