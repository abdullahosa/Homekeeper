"""Render the Homekeeper setup page in a real browser against a mock `hass`."""

from __future__ import annotations

import json
import pathlib

import pytest

playwright = pytest.importorskip("playwright.sync_api")

PANEL = pathlib.Path(__file__).parents[2] / "custom_components/homekeeper/frontend/homekeeper-setup.js"
SHOTS = pathlib.Path(__file__).parent / "out"

DATA = {
    "todo_count": 2,
    "sections": [
        {"kind": "people", "items": [
            {"id": "osamah", "title": "Osamah", "detail": "Owner · English", "issues": []},
            {"id": "dad", "title": "Dad", "detail": "Owner · Arabic", "issues": ["no_notify"]},
        ]},
        {"kind": "modules", "items": [
            {"id": "bills", "title": "Bills", "detail": "2 item(s) · Owners: Dad", "issues": []},
        ]},
        {"kind": "duties", "items": [
            {"id": "mow", "title": "Mow <b>the</b> lawn", "detail": "Lawn · Every 1w", "issues": ["no_owner"]},
        ]},
        {"kind": "billers", "items": []},
    ],
}

HARNESS = """
() => {
  window.calls = [];
  const hass = {
    callWS: async (msg) => { window.calls.push(msg); return JSON.parse(JSON.stringify(window.DATA)); },
    connection: { subscribeEvents: async (cb, ev) => { window.fire = cb; window.subscribed = ev; return () => {}; } },
  };
  const el = document.createElement("homekeeper-setup");
  document.body.append(el);
  el.hass = hass;
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


def _page(browser, *, width=420, store=None):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    # a real origin, so localStorage works like it does in Home Assistant
    page.route(
        "http://ha.test/**",
        lambda route: route.fulfill(
            content_type="text/html", body="<body style='margin:0;font-family:sans-serif'></body>"
        ),
    )
    page.goto("http://ha.test/homekeeper")
    if store is not None:
        page.evaluate(f"localStorage.setItem('homekeeper-setup-open', {json.dumps(json.dumps(store))})")
    page.evaluate(f"window.DATA = {json.dumps(DATA)}")
    page.add_script_tag(path=str(PANEL))
    page.evaluate(HARNESS)
    page.wait_for_selector("homekeeper-setup >> details")
    return page


def _open(page):
    return page.evaluate(
        "Object.fromEntries([...document.querySelector('homekeeper-setup').shadowRoot.querySelectorAll('details')]"
        ".map(d => [d.dataset.kind, d.open]))"
    )


def test_sections_with_something_to_do_start_open_and_finished_ones_closed(browser):
    page = _page(browser)
    assert page.evaluate("window.calls") == [{"type": "homekeeper/setup"}]
    assert page.evaluate("window.subscribed") == "homekeeper_changed"
    # modules are complete -> collapsed; people/duties need work -> open; billers is empty -> open
    assert _open(page) == {"people": True, "modules": False, "duties": True, "billers": True}
    text = page.inner_text("homekeeper-setup >> main")
    assert "2 items still need setting up" in text
    assert "No phone set for notifications" in text
    assert "No owner" in text
    assert "1 to do" in text
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "setup-panel.png"))


def test_names_are_escaped(browser):
    page = _page(browser)
    assert page.locator("homekeeper-setup >> .row b").count() == 0
    assert "Mow <b>the</b> lawn" in page.inner_text("homekeeper-setup >> main")


def test_collapse_all_expand_all_and_remembered_choice(browser):
    page = _page(browser)
    page.click("homekeeper-setup >> text=Collapse all")
    assert set(_open(page).values()) == {False}
    page.click("homekeeper-setup >> details[data-kind=modules] >> summary")
    assert _open(page)["modules"] is True
    page.wait_for_function("JSON.parse(localStorage.getItem('homekeeper-setup-open')).modules === true")
    stored = json.loads(page.evaluate("localStorage.getItem('homekeeper-setup-open')"))
    assert stored["modules"] is True and stored["people"] is False
    page.click("homekeeper-setup >> text=Expand all")
    assert set(_open(page).values()) == {True}


def test_saved_choices_are_applied_on_load(browser):
    page = _page(browser, store={"people": False, "modules": True})
    state = _open(page)
    assert state["people"] is False and state["modules"] is True
    assert state["duties"] is True  # not saved -> default (has something to do)


def test_refreshes_when_homekeeper_changes(browser):
    page = _page(browser)
    page.evaluate("window.DATA.sections[0].items.pop(); window.DATA.todo_count = 2; window.fire()")
    page.wait_for_function(
        "document.querySelector('homekeeper-setup').shadowRoot.textContent.includes('2 items still need')"
    )
    assert len(page.evaluate("window.calls")) == 2
