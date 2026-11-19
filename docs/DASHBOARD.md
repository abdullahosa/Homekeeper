# Dashboard and wall panel

Homekeeper ships a Lovelace card. It is served by the integration and added to every dashboard automatically; there is nothing to install or register. After first setup, hard-refresh the browser once.

A ready-made four-view dashboard is in [dashboard.yaml](dashboard.yaml): Today, Wall panel, Lists and Admin. Paste it into a dashboard's raw configuration editor.

## The card

```yaml
type: custom:homekeeper-card
mode: list            # list (default), wall or bills
title: Homekeeper
person: me            # a person id, or "me" for the logged-in user; omit to show chips for everyone
module: lawn          # pin to one module; omit to show module chips
language: ar          # en or ar; default follows the user's Home Assistant language
horizon_days: 14      # how far ahead "Coming up" looks
confirm: true         # tap Done twice; false for a single tap
```

- **Overdue and due** duties come first, then **Coming up** and snoozed ones.
- **Done** asks for a second tap (the button turns green and says so) and clears itself after 4 seconds. It calls `homekeeper.complete` with method `button`, recorded against the person.
- **Snooze 1 day** appears on overdue and due duties.
- Bills show their amount from BillBot.
- Arabic switches the card to right-to-left, with Arabic titles where a duty has one.
- The card updates itself when anything changes (any tap, notification action, NFC scan, voice command or BillBot message) and refreshes every five minutes as a fallback.

## Bills view

`mode: bills` shows one row per biller, filled from your Homekeeper billers and BillBot's latest message for each, so a new biller appears by itself:

- **Status** (Overdue, Due, Autopay, Paid, No bill yet), **amount** and **due date**, most urgent first, with the total still due at the top (autopay bills are not counted). Income billers such as rent come last, showing the last payment received.
- **Pay ↗** while a bill is open, **Log in ↗** once it is paid (to check it), from the biller's Login page; the password note shows under it.
- **Mark paid** while Homekeeper has the bill open. It asks for a second tap, closes the pay duty and presses BillBot's Mark paid, like Done.
- Each biller's **Arabic name** and **icon** (set on the biller) show next to its name; in Arabic the Arabic name comes first.
- `module:` limits it to one module's billers.

## "me": who is logged in

To make `person: me` work, link each Homekeeper person to their Home Assistant `person.*` entity: Settings > Devices & services > Homekeeper > the person > Reconfigure > Person entity. That person entity is already tied to a login. People with no link simply see everyone.

## Wall panel

`mode: wall` is built for a tablet on a wall: large tiles, a full-width Done button at least 64 px tall, and no small text on the main tiles. Use it on a dashboard view with `panel: true` so it fills the screen.

For a tablet that never shows a login or menus:

1. Create a Home Assistant user for the tablet (non-admin) and log in once on the tablet.
2. Install Kiosk Mode from HACS and hide the header and sidebar for that user.
3. Open the dashboard's "Wall panel" view and set it as the tablet's start page.
4. Turn off screen timeout, or use Fully Kiosk Browser if you want a screen schedule.

The tablet's user is not linked to a person, so Done is recorded without a name. If you would rather have names, put one person's chips on the card with `person:` and have each person tap their own.

## Health on the Admin view

`binary_sensor.homekeeper_healthy` goes off when something needs attention (a biller went silent, BillBot or MQTT is offline, a duty has no owner, notifications are failing). The card also lists the problems in a short banner on the list view.
