# Changelog

## Unreleased

- The duty details form now says which field is wrong (reminder, escalation or months) and keeps what you typed instead of clearing the form. The reminder and escalation labels explain that -3d means 3 days before the due date and 2d means 2 days after.
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
