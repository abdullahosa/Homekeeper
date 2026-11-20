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

### Trash and recycling calendar

Many city trash apps run on ReCollect, which gives every address a calendar link. Its event titles are long ("Loose leaf - zone b - day 3, yard waste - northside, recycling - northside, and garbage - northside") and it may list drop-off and leaf collection days too. Homekeeper can show a tidy copy.

1. Get the calendar link: look up your address on your city's trash schedule page, choose **Get a calendar > Add to Google Calendar**, and copy the link it shows. Delete everything from `?client_id=` onward.
2. Settings > Devices & services > **Add integration > Remote Calendar**, paste the link.
3. Homekeeper > **Add calendar**: name it (for example `Trash pickups`), pick that calendar, and set **Only events containing** to `garbage`. You get `calendar.homekeeper_trash_pickups` with only pickup days, each titled with the carts ("Garbage + Recycling + Yard waste"); the original title is in the event's description. Nothing to check off.
4. Show it with a Calendar card in the list view:

   ```yaml
   type: calendar
   title: Trash pickups
   initial_view: listWeek   # the next 7 days as a list
   entities:
     - calendar.homekeeper_trash_pickups
   ```

If you also want a push on bin night with a Done button, add a duty with schedule type **calendar** instead (or as well): it opens the evening before each pickup, says what goes out, moves when a holiday shifts the pickup, and waits until 18:00 to notify. Same-day delays sent as app alerts may not be in the calendar; keep your city's app for those.

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
