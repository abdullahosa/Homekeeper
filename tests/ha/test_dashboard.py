from pathlib import Path

from homeassistant.setup import async_setup_component

from custom_components.homekeeper.const import DOMAIN, EVENT_CHANGED, STATIC_URL
from custom_components.homekeeper.runtime import get_runtime


async def _start(hass, entry):
    assert await async_setup_component(hass, "homeassistant", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return get_runtime(hass, entry.entry_id)


async def test_overview_over_websocket(hass, hass_ws_client, entry_factory, notify_calls, freezer):
    entry = entry_factory()
    await _start(hass, entry)
    client = await hass_ws_client(hass)
    freezer.move_to("2026-12-02 09:00:00")  # after auth, whose token would expire
    await client.send_json({"id": 1, "type": "homekeeper/overview"})
    msg = await client.receive_json()
    assert msg["success"]
    result = msg["result"]
    assert result["health"] == {"ok": True, "problems": []}
    assert result["me"] is None
    item = next(i for i in result["items"] if i["duty_id"] == "filters")
    assert item["state"] == "overdue" and item["days"] == -1
    assert item["title"]["ar"] == "تغيير الفلاتر"
    assert {p["id"] for p in result["people"]} >= {"a", "b"}


async def test_horizon_is_validated(hass, hass_ws_client, entry_factory):
    await _start(hass, entry_factory())
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "homekeeper/overview", "horizon_days": 9999})
    assert not (await client.receive_json())["success"]


async def test_me_maps_login_to_person(hass, hass_ws_client, hass_admin_user, entry_factory):
    entry = entry_factory()
    sub_ = next(s for s in entry.subentries.values() if s.data["id"] == "a")
    hass.config_entries.async_update_subentry(
        entry, sub_, data={**sub_.data, "person_entity": "person.alex"}
    )
    hass.states.async_set("person.alex", "home", {"user_id": hass_admin_user.id})
    await _start(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "homekeeper/overview"})
    assert (await client.receive_json())["result"]["me"] == "a"


async def test_me_is_none_for_unlinked_user(hass, hass_ws_client, entry_factory):
    entry = entry_factory()
    sub_ = next(s for s in entry.subentries.values() if s.data["id"] == "a")
    hass.config_entries.async_update_subentry(
        entry, sub_, data={**sub_.data, "person_entity": "person.alex"}
    )
    hass.states.async_set("person.alex", "home", {"user_id": "someone-else"})
    await _start(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "homekeeper/overview"})
    assert (await client.receive_json())["result"]["me"] is None


async def test_error_when_not_set_up(hass, hass_ws_client):
    from custom_components.homekeeper import websocket

    websocket.async_register(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "homekeeper/overview"})
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "not_loaded"


async def test_change_event_fires_when_state_changes(hass, entry_factory):
    entry = entry_factory()
    await _start(hass, entry)
    seen = []
    hass.bus.async_listen(EVENT_CHANGED, lambda e: seen.append(e))
    await hass.services.async_call(
        DOMAIN, "complete", {"duty_id": "filters", "by": "a"}, blocking=True
    )
    await hass.async_block_till_done()
    assert seen


async def test_card_is_served_and_registered(hass, hass_client, entry_factory):
    await _start(hass, entry_factory())
    assert hass.data[f"{DOMAIN}_frontend"] is True
    # HA's http component is not running in unit tests; the file itself must exist and be valid JS text
    from pathlib import Path

    card = Path(__file__).parents[2] / "custom_components/homekeeper/frontend/homekeeper-card.js"
    assert card.is_file() and "homekeeper-card" in card.read_text()
    assert STATIC_URL.startswith("/")


async def test_setup_overview_over_websocket(hass, hass_ws_client, entry_factory):
    await _start(hass, entry_factory())
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "homekeeper/setup"})
    msg = await client.receive_json()
    assert msg["success"]
    kinds = [s["kind"] for s in msg["result"]["sections"]]
    assert kinds == ["people", "modules", "duties", "billers"]
    people = next(s for s in msg["result"]["sections"] if s["kind"] == "people")["items"]
    assert {p["id"] for p in people} == {"adm", "a", "b"}
    assert msg["result"]["todo_count"] == 0


async def test_setup_overview_is_admin_only(hass, hass_ws_client, hass_read_only_access_token, entry_factory):
    await _start(hass, entry_factory())
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "homekeeper/setup"})
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "unauthorized"


async def test_setup_page_is_registered_as_an_admin_sidebar_panel(hass):
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.homekeeper import _async_register_frontend
    from custom_components.homekeeper.const import PANEL_FILE, PANEL_PATH

    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.config.components.add("frontend")
    with (
        patch("homeassistant.components.panel_custom.async_register_panel") as panel,
        patch("homeassistant.components.frontend.add_extra_js_url") as js,
    ):
        await _async_register_frontend(hass)
    panel.assert_awaited_once()
    import hashlib

    folder = Path(__file__).parents[2] / "custom_components/homekeeper/frontend"
    card_url = js.call_args.args[1]
    assert card_url == f"{STATIC_URL}/homekeeper-card.js?v=" + hashlib.sha256(
        (folder / "homekeeper-card.js").read_bytes()
    ).hexdigest()[:12]  # changes whenever the card changes, so browsers fetch the new one
    kwargs = panel.call_args.kwargs
    assert kwargs["frontend_url_path"] == PANEL_PATH
    assert kwargs["webcomponent_name"] == "homekeeper-setup"
    assert kwargs["require_admin"] is True
    assert kwargs["module_url"].startswith(f"{STATIC_URL}/{PANEL_FILE}?v=")
    assert kwargs["module_url"] != f"{STATIC_URL}/{PANEL_FILE}?v=0.1.0"

    page = Path(__file__).parents[2] / "custom_components/homekeeper/frontend" / PANEL_FILE
    assert 'customElements.define("homekeeper-setup"' in page.read_text()
