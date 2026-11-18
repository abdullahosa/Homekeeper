# Changelog

## Unreleased

- Adding a duty or biller before any module exists now says to add a module first, instead of showing an empty dropdown with a confusing error.
- Fixed a Home Assistant log warning about reading a file inside the event loop when the card is registered.
- Adding a person no longer asks for an ID; it is made from the name (Arabic names are transliterated, repeats get `_2`). Existing people are unchanged.
- Owner and observer pickers show names instead of IDs.

## 0.1.0

First installable version.

- Duties, modules and people are managed from the Home Assistant UI (config subentries); no YAML needed.
- Schedules: interval, after completion, day of month, yearly window, sensor condition, and outside signal, with early-open conditions, season limits, snooze, skip with a reason, and "not mine" hand-off.
- Reminders and escalation by mobile push in English or Arabic, with Done, Snooze and Not mine buttons and quiet hours.
- To-do lists, a calendar, per-duty and per-person sensors, and a health sensor.
- BillBot bridge over MQTT: bills open and close from BillBot, and marking a bill done presses BillBot's mark-paid. Optional BillBot add-on in `billbot/`.
- NFC tags and Assist voice ("mark the lawn as done", in English and Arabic).
- A dashboard card with a big-button wall-panel mode, right-to-left Arabic, and a ready-made dashboard (`docs/dashboard.yaml`).
- Starter packs bundled with the integration (`bills`, `home`, `lawn-fescue`, `rental`), importable by name.
