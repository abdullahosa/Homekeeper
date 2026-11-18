# Install and first setup

Try this on a spare Home Assistant first. Homekeeper never pays anything or touches your email, but it does send notifications and listen for BillBot messages.

Needs Home Assistant 2026.11 or newer.

## 1. Install

1. In HACS, open the three-dot menu, choose **Custom repositories**, add `https://github.com/abdullahosa/Homekeeper` as an **Integration**, and download Homekeeper.
2. Restart Home Assistant.
3. Settings > Devices & services > **Add integration** > Homekeeper. It asks nothing; it just creates the entry.

## 2. Add people

Open the Homekeeper entry and **Add person**, once per family member. For each, set:

- a name and role (`owner`, `observer` or `admin`; admin sees and edits everything),
- the mobile app notify service (for example `notify.mobile_app_dads_phone`),
- the language (`en` or `ar`),
- quiet hours, if wanted,
- the **Person entity** (their `person.*`), which lets the dashboard card show "mine" for whoever is logged in.

## 3. Add duties

Fastest: import a bundled pack, then edit what it creates. In Developer tools > Actions, run:

```yaml
action: homekeeper.import_pack
data:
  name: lawn-fescue     # or bills, rental, home
  dry_run: true         # first look; run again without it to apply
```

Packs are generic starting points. After importing, open each duty (Homekeeper > the duty > Reconfigure) to set owners, dates and amounts. You can also add duties by hand with **Add duty**, and change or delete any of them later. Packs never overwrite your edits unless you pass `overwrite: true`.

## Keeping track of what is set up

The **Homekeeper** entry in the sidebar (admins only) lists People, Modules, Duties and Billers in
sections you can collapse, and marks anything that still needs setting up (no owner, no phone for
notifications, an empty module). Use it as your checklist. To add or change something, tap the link
at the bottom of a section; that opens the integration page, which is where all editing happens.

## 4. Dashboard

Paste [dashboard.yaml](dashboard.yaml) into a dashboard's raw configuration editor. See [DASHBOARD.md](DASHBOARD.md) for the card options and the wall panel.

## 5. Optional

- **Bills from BillBot:** [../billbot/BILLBOT-PATCH.md](../billbot/BILLBOT-PATCH.md). Needs MQTT.
- **NFC tags and voice:** [NFC-AND-VOICE.md](NFC-AND-VOICE.md).

## Check it works

- `binary_sensor.homekeeper_healthy` is on. If it is off, its `problems` attribute says why.
- Run `homekeeper.complete` on a duty from Developer tools and watch the to-do list and card update.
- Send yourself a test: set a duty's reminder to `0d` with a due date of today and wait for the next check (Homekeeper checks every 5 minutes).
