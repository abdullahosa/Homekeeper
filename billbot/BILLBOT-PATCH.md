# BillBot add-on: biller list from Homekeeper

Optional. Lets you add, edit and remove billers in Home Assistant without editing
`billers.json` or restarting BillBot. BillBot keeps its own mailbox pipeline, Duke PDF
parsing and database; this only changes where the sender list comes from.

Nothing here runs unless you install it. Back up CT 105 first.

## 1. Install (inside the BillBot container)

```bash
cp homekeeper_billers.py /opt/billbot/
cd / && patch -p1 --dry-run < /path/to/load_billers.patch   # check first
patch -p1 < /path/to/load_billers.patch
systemctl restart billbot
```

The patch only splits `load_billers()` in two: the original body becomes
`_load_local_billers()`, and the new `load_billers()` merges Homekeeper's list on top.
If `homekeeper_billers.py` is missing, BillBot behaves exactly as before.

It reuses the `BILLBOT_MQTT_*` settings already in `/etc/billbot/billbot.env`. It keeps
the last good list in `/var/lib/billbot/homekeeper-billers.json`, so a broker outage never
loses your billers.

## 2. Mosquitto ACL

Give BillBot's MQTT user read access to the list. It already owns `billbot/#` and
`homeassistant/device/billbot/#`:

```
user <billbot-user>
topic read homekeeper/billers
```

Homekeeper runs as Home Assistant's own MQTT client. If that user is not unrestricted,
allow it:

```
topic readwrite homekeeper/#
topic read billbot/+/state
topic read billbot/status
topic write billbot/+/mark_paid
```

## 3. Check it

In Homekeeper add a biller with a sender domain, then in the BillBot container:

```bash
mosquitto_sub -h <broker> -u <user> -P '<password>' -t homekeeper/billers -C 1 -W 5
```

You should see the JSON with your domain. Send BillBot a test email from that sender; its
log should no longer print "unknown sender".

## 4. After it works

Move your senders into Homekeeper (Add biller, or import a pack), then empty
`billers.json` to `{}` so there is one place to edit. Homekeeper's list wins on any clash.

## Undo

```bash
rm /opt/billbot/homekeeper_billers.py
patch -R -p1 < /path/to/load_billers.patch
systemctl restart billbot
```

## What each message looks like

| Topic | Direction | Meaning |
|---|---|---|
| `homekeeper/billers` (retained) | Homekeeper to BillBot | `{"version":1,"billers":{"domain":"Name"}}` |
| `billbot/<name>/state` (retained) | BillBot to Homekeeper | status, amount, due_date, arrived, paid |
| `billbot/status` | BillBot to Homekeeper | `online` / `offline` |
| `billbot/<name>/mark_paid` | Homekeeper to BillBot | `PRESS` when someone marks the bill done |

`<name>` is the biller name lowercased with non-alphanumerics replaced by `_`
("Duke Energy" becomes `duke_energy`), the same rule BillBot uses.

## Rent and other income

Zillow rent notices arrive as payment emails. BillBot records a payment with no matching
bill as a paid row dated on the payment day; Homekeeper reads that as "rent received" and
completes the duties listed under **Completes** on the income biller. This depends on the
local model classifying those emails as payments. Verify with the first real rent email
and adjust `extract.py`'s prompt if it is classed as something else.
