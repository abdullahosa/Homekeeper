# Homekeeper: Specification (v0.1 draft)

Homekeeper is a Home Assistant custom integration that keeps a household's recurring duties (maintenance, bills, rental, lawn) from depending on one person. Duties have owners, schedules, reminders, escalation and a history. Everything is editable from the HA UI.

This repository is public. It holds only generic code and generic starter packs. Names, addresses, amounts, filter sizes and anything else personal live in the user's own Home Assistant configuration, never in this repo.

## 1. Principles

1. **Modular.** A duty is data, not code. Adding, editing or removing one never needs a release.
2. **Observe, don't impersonate.** Homekeeper reminds and records. It never pays, never sends money, and never holds credentials for email or banks.
3. **BillBot reads, Homekeeper runs.** BillBot (separate LXC) keeps the mailbox pipeline and Duke PDF parsing. Homekeeper owns owners, reminders, escalation, lists and the dashboard.
4. **Fails loudly.** A silent failure is worse than a noisy one. A health sensor reports stale data, missing signals and unsent notifications.
5. **Family first.** Big buttons, short text, per-person language (English or Arabic), and a wall-panel view that needs no login.

## 2. Concepts

| Concept | Meaning |
|---|---|
| **Module** | A named group of duties (Bills, Rental, Lawn, Home). Has a default owner list and a dashboard section. |
| **Duty** | One recurring responsibility. |
| **Occurrence** | One concrete due instance of a duty, with a state and history. |
| **Person** | A mapping from an HA user and notify service to a role, language and quiet hours. |
| **Biller** | A specialised duty fed by BillBot (incoming bill, then paid or not). Managed as a config subentry. |
| **Pack** | A YAML file that bulk-creates duties. |

## 3. Data model

### 3.1 Duty

| Field | Type | Notes |
|---|---|---|
| `id` | slug | Stable, unique. |
| `module` | slug | Must exist. |
| `title` | `{en, ar?}` | Arabic optional; falls back to English. |
| `owners` | list of person ids | First is the primary. Empty means module default. |
| `observers` | list of person ids | Always notified of overdue and done, never nagged. |
| `schedule` | object | See 3.2. |
| `remind` | list | Offsets before due, e.g. `[-3d, 0d]`. |
| `escalate` | list | After overdue by N days, notify these people. |
| `how_to` | markdown | Shown in the notification detail and card. |
| `done_by` | list | `button`, `nfc`, `voice`, `auto` (a signal completes it). |
| `enabled` | bool | Disabling keeps history. |
| `season` | optional | Months in which the duty is active. |

### 3.2 Schedule types

- `interval`: every N days, weeks or months from a fixed anchor.
- `after_completion`: N days after the last completion (filters, descaling).
- `day_of_month`: one or more days (rent on the 1st and 15th). Option for "next business day".
- `yearly_window`: opens on a date, due by a date (HOA, fertilizer windows).
- `condition`: opens when a sensor condition becomes true (soil temperature, rain, first freeze), with an optional earliest and latest date.
- `signal`: opens when an external event arrives (bill posted, rent received); can auto-complete a paired duty.

Any schedule can carry `open_early_when` (a condition that opens the window ahead of the calendar date) and `not_before` / `not_after` bounds.

### 3.3 Occurrence states

`upcoming` then `due` then `overdue`, ending in `done` or `skipped`. `snoozed` is a temporary overlay on `due` or `overdue` with an expiry. Completion records who, when, method and an optional note. Skipping requires a reason. The next occurrence is computed on completion according to the schedule type.

### 3.4 Person

`id`, `name`, `ha_user`, `notify` (service name), `language` (`en` or `ar`), `role` (`owner`, `observer`, `admin`), `quiet_hours`. Admin sees and edits everything. Roles never grant payment ability, because Homekeeper has none.

## 4. Home Assistant surface

### 4.1 Setup
- Config flow creates the integration entry (people first, then modules).
- **Config subentries**: one type for duties, one for billers. Add, edit and delete from the UI.
- Options flow: global quiet hours, escalation defaults, language defaults, health thresholds.

### 4.2 Entities
- `todo.homekeeper_<module>`: open occurrences as list items. Completing an item completes the duty.
- `calendar.homekeeper`: all occurrences, filterable by module and owner.
- `sensor.homekeeper_<duty>_next_due`, `sensor.homekeeper_<duty>_state` (diagnostic).
- `sensor.homekeeper_overdue_count`, and one per module and per person.
- `binary_sensor.homekeeper_healthy`, with attributes naming the failing check.
- Biller entities keep BillBot's current entity IDs so existing dashboards keep working.

### 4.3 Services
- `homekeeper.complete` (duty, by, method, note)
- `homekeeper.snooze` (duty, until or hours)
- `homekeeper.skip` (duty, reason)
- `homekeeper.reassign` (duty, owners)
- `homekeeper.import_pack` (path or inline YAML, dry_run)
- `homekeeper.export_pack` (module) for backups

### 4.4 Events
`homekeeper_due`, `homekeeper_overdue`, `homekeeper_completed`, `homekeeper_skipped`, `homekeeper_health_failed`. These feed user automations.

### 4.5 Notifications
Mobile push per person, in their language. Actions: **Done**, **Snooze 1 day**, **Not mine**. "Not mine" notifies the next owner and the admin. Overdue pushes repeat on the escalation schedule, bounded by quiet hours. A weekly digest to observers lists what was done and what is late.

### 4.6 Done-by methods
- Button in the notification or card.
- NFC tag scan (tag ids listed on the duty; see docs/NFC-AND-VOICE.md).
- Assist voice: "mark <duty> as done" completes the matching duty (see docs/NFC-AND-VOICE.md).
- Auto: a sensor or BillBot signal completes it.

## 5. BillBot interface

Implemented. BillBot reads, Homekeeper runs.

- A **biller** is a config subentry: name as BillBot files it, kind (`bill` or `income`), sender domains, owners, expected cadence and grace, reminders, escalation. A `bill` biller becomes a "Pay ..." duty (`bill-<id>`); an `income` biller lists the duties it completes (rent).
- Homekeeper publishes a retained `homekeeper/billers` message (`{"version":1,"billers":{domain:name}}`). An optional BillBot add-on (`billbot/`) reads it, so billers are managed in Home Assistant only. Without the add-on BillBot keeps using `billers.json`.
- Homekeeper subscribes to `billbot/+/state` and `billbot/status`. A `due`/`overdue` state opens the duty with the amount; `paid` or `autopay` closes it (method `auto`); a newer bill supersedes an unpaid older one; replayed retained messages change nothing. An income `paid` state completes the listed duties only when the payment is within 7 days of their due date.
- Marking a bill done in Homekeeper (button, to-do, NFC, voice, service) presses BillBot's `billbot/<name>/mark_paid` so BillBot stays the source of truth. A payment BillBot detects closes the duty without pressing again.
- Health reports `biller_silent:<id>` when no bill or payment arrived within cadence plus grace, `billbot_offline` when `billbot/status` is offline, and `mqtt_unavailable`.
- Mosquitto ACL lines are in `billbot/BILLBOT-PATCH.md`.

## 6. Packs

Packs are YAML. They create duties, modules and billers idempotently (keyed by `id`). Public packs are generic: placeholders for amounts, sizes and people. Personal values are filled in after import. Packs shipped in this repo: `bills`, `rental`, `home`, `lawn-fescue`.

## 7. Health checks

- Last BillBot message older than its cadence.
- Any duty with no owner.
- Notification delivery failures.
- A condition duty whose sensor is unavailable.
- An unreachable weather or soil-temperature source.

## 8. Security

- No email credentials, bank data or card numbers anywhere in Homekeeper.
- Secrets stay in HA's secret store or the BillBot host; none in packs or the repo.
- BillBot's `/bill` endpoint keeps its 32-character bearer token and localhost binding.
- The MQTT broker password in plain text on the broker config should be rotated before go-live.

## 9. Acceptance tests (from real events)

1. A utility bill arrives; the duty opens, the owner is pushed, a matching payment closes it.
2. Rent day arrives on the 1st; duty opens, and if no income signal arrives within the grace period it escalates.
3. A duty is completed by NFC scan and the next occurrence moves forward.
4. An owner taps "Not mine"; the next owner and admin are notified.
5. Dad's push arrives in Arabic; others in English.
6. A biller stops sending; the health sensor goes false within cadence plus grace.
7. Pack import twice produces no duplicates.
8. Soil temperature five-day average crosses the threshold; the pre-emergent window opens early.

## 10. Build phases

0. Repo skeleton, spec, packs. (done)
1. Core engine: duties, schedules, occurrences, storage, pure Python with tests. (done)
2. HA integration: config flow, subentries, entities, services, notifications. (done)
3. NFC tags and Assist voice. (done)
4. BillBot bridge and biller subentries. (done)
5. Dashboard card, wall panel, packs polish, release via HACS.

Gate: test on a spare HA instance first, then production before the move-out date.
