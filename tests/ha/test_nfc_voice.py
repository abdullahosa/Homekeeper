
from helpers import sub
from homeassistant.components import conversation
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from custom_components.homekeeper.runtime import get_runtime


def with_tags(entry_factory, tags=("tag-filters",), done_by=("button", "nfc", "voice")):
    return entry_factory(
        extra=(
            sub(
                "duty",
                "mow",
                {
                    "module": "home",
                    "title": {"en": "Mow the lawn", "ar": "قص العشب"},
                    "schedule": {"type": "after_completion", "every": "7d", "first_due": "2026-12-01"},
                    "remind": ["0d"],
                    "done_by": ["button", "voice"],  # no nfc
                    "nfc_tags": ["tag-mow"],
                },
                "Mow the lawn",
            ),
        )
    )


async def assist(hass):
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})


async def start(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return get_runtime(hass, entry.entry_id)


async def say(hass, text, language="en"):
    result = await conversation.async_converse(hass, text, None, Context(), language=language)
    return result.response.speech["plain"]["speech"]


async def test_tag_completes_its_duty_once(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    entry = entry_factory()
    sub_ = next(s for s in entry.subentries.values() if s.data["id"] == "filters")
    hass.config_entries.async_update_subentry(
        entry, sub_, data={**sub_.data, "nfc_tags": ["tag-filters"]}
    )
    rt = await start(hass, entry)
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-filters", "device_id": "x"})
    await hass.async_block_till_done()
    assert rt.engine.history[-1].method == "nfc"
    assert rt.engine.occurrences["filters"].due.isoformat() == "2027-03-01"
    # a second scan seconds later must not complete the next occurrence early
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-filters"})
    await hass.async_block_till_done()
    assert len([h for h in rt.engine.history if h.duty_id == "filters"]) == 1
    # unknown tags and non-tag events are ignored
    hass.bus.async_fire("tag_scanned", {"tag_id": "who-knows"})
    hass.bus.async_fire("tag_scanned", {})
    await hass.async_block_till_done()


async def test_tag_on_duty_that_disallows_nfc_is_ignored(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    rt = await start(hass, with_tags(entry_factory))
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-mow"})
    await hass.async_block_till_done()
    assert not [h for h in rt.engine.history if h.duty_id == "mow"]


async def test_duplicate_tag_is_reported_not_crashing(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    entry = with_tags(entry_factory)
    sub_ = next(s for s in entry.subentries.values() if s.data["id"] == "filters")
    hass.config_entries.async_update_subentry(
        entry, sub_, data={**sub_.data, "nfc_tags": ["tag-mow"]}
    )
    rt = await start(hass, entry)
    assert any("tag-mow" in p for p in rt.invalid)
    assert hass.states.get("binary_sensor.homekeeper_healthy").state == "off"


async def test_voice_marks_done_and_snoozes(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    await assist(hass)
    rt = await start(hass, with_tags(entry_factory))
    assert await say(hass, "mark mow the lawn as done") == "Marked Mow the lawn as done."
    assert rt.engine.history[-1].duty_id == "mow" and rt.engine.history[-1].method == "voice"
    assert await say(hass, "mark the lawn done") == "Mow the lawn was just marked done."
    out = await say(hass, "snooze replace filters until tomorrow")
    assert out == "Snoozed Replace filters until tomorrow."
    assert hass.states.get("sensor.homekeeper_replace_filters_state").state == "snoozed"


async def test_voice_query_ambiguous_and_missing(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    await assist(hass)
    await start(hass, with_tags(entry_factory))
    out = await say(hass, "what is overdue")
    assert "Replace filters" in out and "Mow the lawn" in out
    assert await say(hass, "mark washing the car as done") == "I couldn't find a task called washing the car."
    out = await say(hass, "what chores are due", "en")
    assert out.startswith("Needs doing:")


async def test_voice_nothing_due_and_arabic(hass, entry_factory, freezer):
    freezer.move_to("2026-11-14 09:00:00")  # nothing due yet
    await assist(hass)
    await start(hass, with_tags(entry_factory))
    assert await say(hass, "what is overdue") == "Nothing is due or overdue."
    freezer.move_to("2026-12-02 09:00:00")
    out = await say(hass, "ما هي المهام المتأخرة", "ar")
    assert out.startswith("المطلوب:") and "قص العشب" in out


async def test_voice_respects_done_by(hass, entry_factory, freezer):
    freezer.move_to("2026-12-01 09:00:00")
    await assist(hass)
    entry = entry_factory(
        extra=(
            sub("duty", "locked", {
                "module": "home", "title": {"en": "Check the roof"},
                "schedule": {"type": "after_completion", "every": "7d", "first_due": "2026-12-01"},
                "done_by": ["button"]}, "Check the roof"),
        )
    )
    await start(hass, entry)
    out = await say(hass, "mark check the roof as done")
    assert out.startswith("I couldn't do that")
