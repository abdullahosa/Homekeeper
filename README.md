# Homekeeper

A Home Assistant integration that keeps a household's recurring duties (maintenance, bills, rental, lawn) from depending on one person: owners, schedules, reminders, escalation and history, all editable from the HA UI.

**Status:** early build. Phases 0 and 1 are in place: spec, starter packs, and a tested pure-Python engine (`custom_components/homekeeper/engine`). The Home Assistant wiring comes next.

- Spec: [docs/SPEC.md](docs/SPEC.md)
- Starter packs: [packs/](packs/) (generic only; personal details stay in your own HA)

Install (once released): add this repository to HACS as a custom repository, then add the Homekeeper integration.

This repository is public. Do not commit names, addresses, amounts or credentials.
