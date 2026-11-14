# NFC tags and Assist voice

## NFC tags
1. Stick an NFC tag (NTAG215 works well) where the job happens: on the filter cabinet, the mower shelf, the hose timer.
2. In Home Assistant open **Settings > Tags**, add the tag (scan it with the Companion app), and copy its ID.
3. Open the Homekeeper integration, edit the duty, and paste the ID into **NFC tag IDs** on the last step. Make sure `nfc` is ticked under "Can be marked done by".
4. Scan the tag when the job is done. The duty completes and the next date is set.

Rules:
- One tag belongs to one duty. A duplicate shows up as a problem on the health sensor.
- A second scan within 10 minutes is ignored, so a double tap cannot complete the next occurrence early.
- A scan on a duty with nothing open, or one that does not allow `nfc`, does nothing.
- Bill duties work too: scanning completes the duty and presses BillBot's Mark paid.

## Assist voice
Homekeeper adds these sentences to Assist. They are deliberately specific, because a matched sentence always answers the request.

| Say | Result |
|---|---|
| "mark replace filters as done" (or "mark ... done", "... finished", "... complete") | Completes the matching duty |
| "snooze replace filters until tomorrow" (or "snooze ... for a day") | Hides its reminders for a day |
| "what is overdue" / "what chores are due" / "what tasks do we have" | Lists what needs doing |
| Arabic: "أنجزت ..." / "أجل ... ليوم" / "ما هي المهام المتأخرة" | Same, in Arabic (first draft, needs a native read) |

You do not have to say the whole title. "Mark the filters as done" finds "Replace HVAC filters". If two duties fit, Assist asks which one. The duty must allow `voice` under "Can be marked done by".

Voice and NFC completions record no person, because neither knows who spoke or scanned.
