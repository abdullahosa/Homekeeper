"""Render the Homekeeper card in a real browser against a mock `hass`.

Skipped when Playwright or its Chromium is not installed.
"""

from __future__ import annotations

import json
import pathlib

import pytest

playwright = pytest.importorskip("playwright.sync_api")

CARD = pathlib.Path(__file__).parents[2] / "custom_components/homekeeper/frontend/homekeeper-card.js"
SHOTS = pathlib.Path(__file__).parent / "out"

DATA = {
    "today": "2026-11-14",
    "me": "sam",
    "health": {"ok": True, "problems": []},
    "people": [
        {"id": "sam", "name": "Sam"},
        {"id": "dad", "name": "Dad"},
        {"id": "alex", "name": "Alex"},
    ],
    "modules": [
        {"id": "lawn", "title": {"en": "Lawn", "ar": "العشب"}},
        {"id": "rental", "title": {"en": "Rental", "ar": "العقار"}},
        {"id": "bills", "title": {"en": "Bills", "ar": "الفواتير"}},
    ],
    "counts": {"overdue": 1, "due": 2},
    "items": [
        {"duty_id": "rent-check", "module": "rental", "module_title": {"en": "Rental"},
         "title": {"en": "Confirm rent arrived", "ar": "تأكيد وصول الإيجار"}, "owners": ["sam", "dad"],
         "state": "overdue", "due": "2026-11-12", "days": -2, "snoozed_until": None, "amount": None,
         "how_to": "", "done_by": ["button"], "biller": None},
        {"duty_id": "bill-duke", "module": "bills", "module_title": {"en": "Bills"},
         "title": {"en": "Pay Duke Energy", "ar": "دفع فاتورة الكهرباء"}, "owners": ["dad"],
         "state": "due", "due": "2026-11-14", "days": 0, "snoozed_until": None, "amount": 142.5,
         "how_to": "", "done_by": ["button"], "biller": "duke"},
        {"duty_id": "mow", "module": "lawn", "module_title": {"en": "Lawn"},
         "title": {"en": "Mow the lawn", "ar": "قص العشب"}, "owners": ["sam"],
         "state": "due", "due": "2026-11-14", "days": 0, "snoozed_until": None, "amount": None,
         "how_to": "", "done_by": ["button"], "biller": None},
        {"duty_id": "hvac", "module": "rental", "module_title": {"en": "Rental"},
         "title": {"en": "Change AC filters", "ar": "تغيير فلاتر المكيف"}, "owners": ["alex"],
         "state": "upcoming", "due": "2026-11-20", "days": 6, "snoozed_until": None, "amount": None,
         "how_to": "", "done_by": ["button"], "biller": None},
        {"duty_id": "trash", "module": "lawn", "module_title": {"en": "Lawn"},
         "title": {"en": "Put bins out", "ar": "إخراج الحاويات"}, "owners": ["sam"],
         "state": "snoozed", "due": "2026-11-13", "days": -1, "snoozed_until": "2026-11-15",
         "amount": None, "how_to": "", "done_by": ["button"], "biller": None},
    ],
}

HARNESS = """
(cfg) => {
  window.calls = [];
  const hass = {
    language: cfg.language || "en",
    callWS: async (msg) => { window.calls.push(["ws", msg]); if (window.failWS) { throw {code: "failed"}; }
      return JSON.parse(JSON.stringify(window.DATA)); },
    callService: async (d, s, data) => { window.calls.push([d, s, data]);
      window.DATA.items = window.DATA.items.filter(i => i.duty_id !== data.duty_id); },
    connection: { subscribeEvents: async (cb, ev) => { window.fire = cb; window.subscribed = ev; return () => {}; } },
  };
  const el = document.createElement("homekeeper-card");
  el.setConfig(cfg);
  document.body.append(el);
  el.hass = hass;
  window.card = el;
}
"""


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as err:  # pragma: no cover - browser missing
            pytest.skip(f"chromium unavailable: {err}")
        yield b
        b.close()


def _page(browser, cfg, *, width=420, height=900, scale=1):
    ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale)
    page = ctx.new_page()
    page.set_content("<body style='margin:0;font-family:sans-serif'></body>")
    page.evaluate(f"window.DATA = {json.dumps(DATA)}")
    page.add_script_tag(path=str(CARD))
    page.evaluate(HARNESS, cfg)
    page.wait_for_selector("homekeeper-card >> .card")
    return page


def _text(page):
    return page.inner_text("homekeeper-card >> .card")


def test_list_mode_sections_and_filters(browser):
    page = _page(browser, {"mode": "list"})
    text = _text(page)
    assert "Confirm rent arrived" in text and "2 days late" in text
    assert "$142.50" in text
    assert "coming up" in text.lower() and "In 6 days" in text
    assert "Snoozed until" in text and "2026-11-15" in text
    assert page.evaluate("window.subscribed") == "homekeeper_changed"
    page.click("homekeeper-card >> .chips >> nth=0 >> text=Dad")
    text = _text(page)
    assert "Pay Duke Energy" in text and "Mow the lawn" not in text
    page.click("homekeeper-card >> text=Everyone")
    page.click("homekeeper-card >> .chips >> nth=1 >> text=Lawn")
    text = _text(page)
    assert "Mow the lawn" in text and "Pay Duke Energy" not in text


def test_done_needs_two_taps_then_calls_service(browser):
    page = _page(browser, {"mode": "list"})
    row = "homekeeper-card >> .row:has-text('Mow the lawn')"
    page.click(f"{row} >> button.act:not(.ghost)")
    assert not [c for c in page.evaluate("window.calls") if c[0] == "homekeeper"]
    assert "Tap again to confirm" in page.inner_text(row)
    page.click(f"{row} >> button.act:not(.ghost)")
    page.wait_for_function("!document.querySelector('homekeeper-card').shadowRoot.textContent.includes('Mow the lawn')")
    calls = [c for c in page.evaluate("window.calls") if c[0] == "homekeeper"]
    assert calls == [["homekeeper", "complete", {"duty_id": "mow", "method": "button", "by": "sam"}]]


def test_single_tap_when_confirm_disabled_and_snooze(browser):
    page = _page(browser, {"mode": "list", "confirm": False})
    page.click("homekeeper-card >> .row:has-text('Pay Duke Energy') >> button.ghost")
    page.wait_for_function("!document.querySelector('homekeeper-card').shadowRoot.textContent.includes('Pay Duke')")
    calls = [c for c in page.evaluate("window.calls") if c[0] == "homekeeper"]
    assert calls == [["homekeeper", "snooze", {"duty_id": "bill-duke", "hours": 24}]]


def test_person_me_filters_to_logged_in_person(browser):
    page = _page(browser, {"mode": "list", "person": "me"})
    text = _text(page)
    assert "Mow the lawn" in text and "Pay Duke Energy" not in text
    assert "Everyone" not in text  # person chips are hidden when the card is pinned


def test_event_triggers_refresh(browser):
    page = _page(browser, {"mode": "list"})
    page.evaluate("window.DATA.items = []")
    page.evaluate("window.fire()")
    page.wait_for_function("document.querySelector('homekeeper-card').shadowRoot.textContent.includes('All caught up')")


def test_error_banner_and_not_loaded(browser):
    page = _page(browser, {"mode": "list"})
    page.evaluate("window.failWS = true; window.fire()")
    page.wait_for_selector("homekeeper-card >> .err")
    assert "That did not work" in _text(page)


def test_arabic_is_rtl_with_arabic_text(browser):
    page = _page(browser, {"mode": "list", "language": "ar"})
    assert page.get_attribute("homekeeper-card >> .card", "dir") == "rtl"
    text = _text(page)
    assert "دفع فاتورة الكهرباء" in text and "متأخرة 2 يوم" in text and "تم" in text


def test_wall_mode_has_big_touch_targets_and_screenshots(browser):
    SHOTS.mkdir(exist_ok=True)
    page = _page(browser, {"mode": "wall", "title": "Home"}, width=1280, height=800, scale=1)
    box = page.locator("homekeeper-card >> .tile button.act:not(.ghost)").first.bounding_box()
    assert box["height"] >= 56
    page.screenshot(path=str(SHOTS / "wall.png"))
    page2 = _page(browser, {"mode": "list"}, scale=2)
    page2.screenshot(path=str(SHOTS / "list.png"), full_page=True)
    page3 = _page(browser, {"mode": "list", "language": "ar"}, scale=2)
    page3.screenshot(path=str(SHOTS / "list-ar.png"), full_page=True)


def test_bill_row_has_log_in_link_and_password_note(browser):
    page = _page(browser, {"mode": "list"})
    page.evaluate("""() => {
      const duke = window.DATA.items.find(i => i.duty_id === 'bill-duke');
      duke.login_url = 'https://example.com/login';
      duke.login_note = 'Bitwarden > Home Bills > Duke Energy';
      const mow = window.DATA.items.find(i => i.duty_id === 'mow');
      mow.login_url = 'javascript:alert(1)';
      window.fire();
    }""")
    row = "homekeeper-card >> .row:has-text('Pay Duke Energy')"
    page.wait_for_selector(f"{row} >> .login a")
    link = page.locator(f"{row} >> .login a")
    assert link.inner_text() == "Log in ↗"
    assert link.get_attribute("href") == "https://example.com/login"
    assert link.get_attribute("target") == "_blank"
    assert link.get_attribute("rel") == "noopener noreferrer"
    assert "Bitwarden > Home Bills > Duke Energy" in page.inner_text(row)
    # a non-web link is never rendered
    assert page.locator("homekeeper-card >> .row:has-text('Mow the lawn') >> a").count() == 0
    # a note alone shows without a link
    page.evaluate("""() => {
      const f = window.DATA.items.find(i => i.duty_id === 'hvac');
      f.login_note = 'Ask Alex'; window.fire();
    }""")
    page.wait_for_function("document.querySelector('homekeeper-card').shadowRoot.textContent.includes('Ask Alex')")
    assert page.locator("homekeeper-card >> .row:has-text('Change AC filters') >> a").count() == 0
    # rows without a login have no link
    assert page.locator("homekeeper-card >> .row:has-text('Put bins out') >> .login").count() == 0
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "card-login.png"))


def test_log_in_label_in_arabic(browser):
    page = _page(browser, {"mode": "list", "language": "ar"})
    page.evaluate("""() => {
      window.DATA.items.find(i => i.duty_id === 'bill-duke').login_url = 'https://example.com/login';
      window.fire();
    }""")
    page.wait_for_selector("homekeeper-card >> .login a")
    assert page.inner_text("homekeeper-card >> .login a") == "تسجيل الدخول ↗"


def test_calendar_duty_row_says_what_is_collected(browser):
    for lang, expected in (("en", "Garbage + Recycling"), ("ar", "النفايات + إعادة التدوير")):
        page = _page(browser, {"mode": "list", "language": lang})
        page.evaluate("""() => {
          const bins = window.DATA.items.find(i => i.duty_id === 'trash');
          bins.what = 'Garbage, Recycling'; bins.event = '2026-11-24'; bins.state = 'due'; bins.days = 0;
          window.fire();
        }""")
        page.wait_for_function(
            f"document.querySelector('homekeeper-card').shadowRoot.textContent.includes({expected!r})"
        )
        if lang == "en":
            SHOTS.mkdir(exist_ok=True)
            page.screenshot(path=str(SHOTS / "card-bins.png"))
