# Viva Q&A

Anticipated questions, with honest answers. The guiding rule throughout: never claim something is real
that isn't, and never apologise for a scoped-out feature — explain the decision and what replaced it.

### "Why didn't you use camera-based emergency vehicle detection like you originally planned?"
We searched this machine, Downloads, Documents, and the reference GitHub repo we were going to source
data from — its dataset folders are gitignored, so cloning the repo never actually downloaded the
images. With no usable ambulance/fire/police image dataset, training a classifier would have meant
either fabricating performance numbers or shipping an undertrained, unreliable model making safety-
relevant decisions. We made the RFID-only path the actual mechanism for objective 5, not a fallback:
`emergency/authorised.py` validates a vehicle ID + tag against a registry before any signal is ever
pre-empted. This is arguably a *more* defensible design for a safety system — vision alone should
probably never unilaterally grant traffic priority anyway, even if the dataset had existed.

### "How accurate is your vehicle detector really?"
Per-class mAP50 on the UVH-26 validation set, measured with a from-scratch IoU-matching evaluator (so
COCO's missing `auto` class is fairly excluded rather than counted as automatic misses): car 0.890,
bike 0.830, auto 0.861, bus 0.760, truck 0.770 — all well above the stock COCO model mapped to the same
classes (car 0.594, bike 0.092, no auto class at all). Ultralytics' own validator separately reports an
overall 0.901 mAP50, using a different methodology — we report both rather than picking the flattering
one. **One gap we're upfront about**: a template for manually counting ~20 real frames per lane
(`count_check_sheet.csv`) was generated but never filled in, so we don't have a ground-truth comparison
specifically on *our* lane videos — only on UVH-26's validation split, which matches the training
distribution by construction.

### "What's actually simulated vs real in this project?"
See `docs/OBJECTIVES_MAP.md`'s real/simulated table and `README.md`'s summary. Short version: detection,
signal control, violations, and accident heuristics run on 4 real recorded videos at J1. Three further
junctions, GPS, and RFID hardware are simulated because this is explicitly a software-only capstone
project — we were never meant to wire up physical sensors.

### "If I unplug the internet, what happens?"
Nothing breaks — the database (`db/sql_client.py`'s SQLite file), the backend, and the website-to-backend
link are all entirely local now, so RFID approvals, commands, and everything else keep working offline.
The only thing that genuinely needs the internet is the OpenWeather Air Pollution API call for real AQI
readings, and even that degrades gracefully to a clearly-labelled simulated fallback
(`airquality/aqi.py`) rather than crashing. Every module also still checks `self.enabled`/catches
exceptions before any database or external-API call, and the detector falls back from GPU to CPU
automatically, so there's no single point of failure even on a flaky connection.

### "Why SQLite instead of Firestore (or another cloud database)?"
We actually started on Firestore (free Firebase plan) for its real-time listeners and declarative
Security Rules, and it worked well for most of the build — until a day of heavy testing exhausted the
free tier's 20,000-writes/day quota (partly from a real bug, a virtual-junction loop writing every tick
instead of on phase change) and froze the live dashboard for hours with no way to force an early reset.
Rather than add a second mechanism just to avoid hitting that wall again, we migrated to a local SQLite
database: zero cost ceiling, zero cloud dependency, and it runs entirely on the demo machine. The
trade-off is honest: SQLite has no native real-time push, so the website now polls a small JSON API
(`backend/api/server.py`) every 2 seconds instead of getting instant updates, and role-based access
control is enforced in that same API layer instead of a declarative rules file. For this project's scale
(a handful of junctions, a few concurrent demo users) that trade-off is clearly worth it.

### "How do you guarantee the signal safety rules actually hold?"
Four rules, stated in `CLAUDE.md` §9 and enforced in `signals/controller.py`, not just documented:
(1) only one approach green/yellow at a time — asserted every tick; (2) green always passes through
yellow before red, including pre-emption and manual override; (3) overrides capped at
`MAX_OVERRIDE_SECONDS` and rejectable; (4) only RFID-authorised vehicles get a multi-junction corridor.
`backend/tests/test_controller.py` has 10 tests specifically exercising these with a fake clock, so
they're checked on every run, not just by inspection.

### "What bugs did you actually find and fix, not just features you added?"
Several, documented with before/after in `CLAUDE.md`'s history and this project's commit history:
- The green corridor's pre-emption had zero lead time in the evaluator (checked the condition only at
  the moment of arrival, not while still approaching), producing a nonsensical *negative* average time
  saved (-32.8s); fixed with a proper time-stepped simulation (now +122.1s average, correctly positive).
- The accident collision heuristic's "speed dropped" check compared only against the immediately
  previous tick, so a sustained collision lost its signal after one tick and could never reach the
  confirmation threshold; fixed with a frozen baseline speed.
- Red-light violations were being detected and evidence saved to disk, but the result was silently
  discarded — the Firestore `violations` collection was permanently empty regardless of what the
  frontend did. Found while building the Violations dashboard page; fixed by actually consuming the
  detector's return value.
- The accident resolve/report listeners existed in `accidents/manager.py` but nothing ever started
  them, and `firestore.rules` additionally blocked the exact write the "Mark resolved" button needed —
  found while building the Accidents dashboard page, fixed on both sides.
- The entire web app had no `.env.local` — every page's Firestore calls were silently failing — found
  during the "Polish + Deploy" phase by actually checking, not assumed from a successful `npm run build`
  (which only checks that the code compiles, not that it does anything at runtime).

### "Why does the dashboard's emergency-requests panel not have approve/reject buttons?"
Because that would be a non-functional UI pretending to do something the backend doesn't actually
support. `emergency/authorised.py` auto-resolves every request purely by RFID match within ~2 seconds,
regardless of source — there's no human-in-the-loop step to approve, because vision-sourced requests
(the one case that would need one) never happen, T4 having been skipped. We built what's honestly there:
a live read-only feed, with a note explaining why.

### "What would you do with another month?"
Fill in the manual count-check sheet against the real lane videos; run `tools/roi_picker.py`'s
calibration workflow and re-verify it against a second camera angle if one were available; wire up
accident evidence-image capture (the API endpoint and storage path already exist, just nothing writes
to them yet); and revisit whether a 6-junction grid (as originally scoped) is worth the extra simulated
complexity versus the 4 actually configured.
