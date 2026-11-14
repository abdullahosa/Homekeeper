# Homekeeper

A Home Assistant integration that keeps a household's recurring duties (maintenance, bills, rental, lawn) from depending on one person: owners, schedules, reminders, escalation and history, all editable from the HA UI.

**Status:** version 0.1.0, ready to try on a spare Home Assistant. It has not yet been run on a live instance, so test before relying on it.

What it does: keeps recurring duties (lawn, rental, bills, home maintenance) from depending on one person, with owners, schedules, reminders in English or Arabic, escalation, history, a wall-panel dashboard, optional BillBot, NFC and voice support. Everything is edited from the Home Assistant UI.

- Install and first setup: [docs/INSTALL.md](docs/INSTALL.md)
- Dashboard and wall panel: [docs/DASHBOARD.md](docs/DASHBOARD.md)
- NFC tags and voice: [docs/NFC-AND-VOICE.md](docs/NFC-AND-VOICE.md)
- Spec: [docs/SPEC.md](docs/SPEC.md)
- BillBot add-on and install notes: [billbot/BILLBOT-PATCH.md](billbot/BILLBOT-PATCH.md)
- Starter packs: [custom_components/homekeeper/packs/](custom_components/homekeeper/packs/) (generic only; import by name; personal details stay in your own HA)

Install: add this repository to HACS as a custom repository, then add the Homekeeper integration (see the install guide).

This repository is public. Do not commit names, addresses, amounts or credentials.

## License

MIT, see [LICENSE](LICENSE).
