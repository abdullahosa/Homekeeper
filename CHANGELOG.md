# Changelog

## Unreleased

- Calendar duties name the carts: a ReCollect title such as "Loose leaf - wednesday week - day 3, yard waste - concord, bulky waste - concord, recycling - concord, and garbage - concord" becomes "Garbage + Recycling + Yard waste + Bulky waste" (Arabic for Arabic readers). Leaf-vacuum days, drop-off events and the area name are left out; words it does not know are shown as written.
- New duty schedule **calendar**: a duty follows a Home Assistant calendar, such as the CARTology (ReCollect) trash pickup calendar added with Remote Calendar. It opens the evening before each pickup (or any lead you choose), says what is collected ("Put the bins out: Garbage + Recycling", in Arabic for Arabic readers), moves when a holiday moves the pickup (with a "schedule changed" push when it was imminent) and skips a pickup that passed. Pushes wait until the duty's time (default 18:00); an overdue push waits until 6:00 the next morning. A push that was waiting is dropped if the duty is done first. An unavailable calendar shows up as a health problem.
- **Bills view** for the dashboard card (`mode: bills`): one row per biller with status, amount, due date, a Pay / Log in link, the password note and Mark paid, filled from Homekeeper's billers and BillBot's latest message, so new billers show up without editing the card. Rent and other income billers show the last payment received. Homekeeper now keeps each biller's latest BillBot state (also across restarts).
- Billers have optional **Arabic name** and **icon** fields. The Arabic name is also used in Arabic pay reminders ("سداد فاتورة الكهرباء").
- Billers have two optional fields: **Login page** and **Where the password is kept**. They show on the bill's to-do item and calendar entry, and on the dashboard card as a "Log in" link with the note under it. An income biller's login shows on the duties it completes (for example the rent check). Only `http://` and `https://` links are accepted. Homekeeper never stores passwords: every Home Assistant user can read these fields, so the note says where the password is (for example a shared password manager), not what it is.
- The biller form keeps what you typed when it shows an error.
- A **Homekeeper** page in the sidebar (admins only) shows People, Modules, Duties and Billers in collapsible sections, with what each row still needs: no phone for notifications, no owner, an empty module, an income biller that completes nothing. Sections with something to do start open and finished ones start closed; Expand all and Collapse all are at the top, and your choices are remembered. Adding and editing still happens on the integration page, one tap away.
- The list of people, modules, duties and billers on the integration page is now grouped by kind: rows are titled "Person · Dad", "Module · Lawn", "Duty · Lawn · Mow the lawn" and "Biller · Duke Energy". Existing rows are renamed on the next restart, and duties follow when their module is renamed.
- Adding a duty or biller before any module exists now asks for the module name first and creates it (Bills for a biller, Home for a duty), instead of showing an empty dropdown.
- Fixed a Home Assistant log warning about reading a file inside the event loop when the card is registered.
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
