# Homekeeper

A Home Assistant integration that keeps a household's recurring duties (maintenance, bills, rental, lawn) from depending on one person: owners, schedules, reminders, escalation and history, all editable from the HA UI.

**Status:** early build. The tested engine and the Home Assistant integration (setup screens for people, modules and duties; to-do, calendar and sensor entities; services; notifications in English and Arabic; pack import) are in place. Not yet released; try it on a spare Home Assistant instance first. The BillBot bridge (bills open and close from BillBot's MQTT state; optional BillBot add-on in `billbot/`) is in. NFC tags and Assist voice are in ([docs/NFC-AND-VOICE.md](docs/NFC-AND-VOICE.md)). The dashboard card and wall-panel view are next.

- Spec: [docs/SPEC.md](docs/SPEC.md)
- BillBot add-on and install notes: [billbot/BILLBOT-PATCH.md](billbot/BILLBOT-PATCH.md)
- Starter packs: [packs/](packs/) (generic only; personal details stay in your own HA)

Install (once released): add this repository to HACS as a custom repository, then add the Homekeeper integration.

This repository is public. Do not commit names, addresses, amounts or credentials.
