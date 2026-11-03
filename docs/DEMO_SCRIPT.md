# Demo Script

A ~12–15 minute walkthrough for the viva, in order. Each step says what to run/click and what the
examiner should see. Commands assume `backend\venv` is active and you're in `backend\`, unless noted.

## 0. Before the room fills up
```powershell
cd backend
venv\Scripts\activate
python main.py --no-display
```
Leave this running in a terminal for the whole demo — it's the entire backend (J1 pipeline, J2–J4
simulation, local API, hourly prediction loop). Open https://nexiora-traffic.web.app in a browser tab
and `http://localhost:5173` in another if you also want to show `npm run dev` live-reloading (optional).

## 1. Public portal — Live Overview (`/`)
Point out: total vehicles (real PCU sum from J1 + simulated J2–J4), signal modes, AQI badge, the live
J1 video tile. Say explicitly: "J1 is 4 real recorded traffic videos; J2–J4 are simulated — no cameras
there, by design, since this is a software-only project."

## 2. Signals (`/signals`)
Switch between junctions. Point out the animated lights with countdown, PCU load per lane, and click
"How it works" to show the plain-English explanation of PCU-weighted green time and no-starvation.

## 3. Login as controller
Go to `/login`, sign in as `controller@nexiora.demo` / `Nexiora#Ctrl2026`. Land on Command Centre.

## 4. Command Centre
Point out the 6 KPI tiles, the live video, the junction grid (click one to jump to Junction Detail).

## 5. Junction Detail — manual override (objective 3 + safety rules)
Open J1. Pick a lane, set a duration (≤60s), click **Force green**. Watch the command flip from
`pending` → `done` within ~2 seconds (the backend's `signals/commands.py` listener, polling live).
Click **Release** to hand control back to the adaptive controller. Say: "this write went through
the database to a real listener in the Python process — it's not a mocked button."

## 6. Red-light violation (objective 7)
If `config.VIOLATION_TEST_MODE = True` in `config.py`, one lane is already held red for a forced demo
window — otherwise just wait for a natural one on the real footage. Switch to `/dashboard/violations`
and show a new row appear with evidence images (click to expand full frame + crop).

## 7. Ambulance priority (objective 5 + 6 + safety rule 4) — the centrepiece
In a second terminal:
```powershell
python -m emergency.ambulance_sim --vehicle AMB001 --tag RFID-AMB-001 --to J4
```
Narrate while it runs: the request is validated against the RFID registry (`authorised_vehicles`) —
**not** by camera recognition, because that model was never trained (be upfront about this if asked,
see `docs/VIVA_QA.md`). Switch to `/dashboard/map` or `/dashboard/emergencies` to show the live ambulance
marker moving along its route and junctions being pre-empted (yellow before red, never a hard cut).
Also try the rejection path for contrast:
```powershell
python -m emergency.ambulance_sim --vehicle AMB001 --tag WRONG-TAG --to J4 --unauthorised
```
Show the request lands as `rejected` with a reason, and a `security` alert is raised — nothing gets
priority just because it asked.

## 8. Accident detection + reroute (objective 14)
```powershell
python -m accidents.accident_sim --road J1_J2 --severity high
```
Switch to `/dashboard/accidents`: show the new active accident, predicted delay, and the detour drawn
on the mini-map (`network/router.py` excluding the now-blocked road). Click **Mark resolved** and show
it drop out of "active" within ~2 seconds (a real database-driven listener, not a local-only toggle).

## 9. Prediction (objective 4)
`/predictions`: short-term (5/10 min) chips per lane — explain these come from a live rolling buffer of
J1's real per-minute counts, not canned numbers. The 24h chart with shaded peak hours comes from the
peak-hour model, which now runs automatically every hour inside `main.py`.

## 10. Air quality / eco mode (objective 8)
`/air`: show the AQI badge and say whether it's `live` (OpenWeather) or `simulated` for this run —
whichever it is, say so out loud; don't let the audience assume it's always live.

## 11. Performance & Reports (objective 11 + 13)
`/dashboard/performance`: adaptive-vs-fixed wait chart and fuel/CO₂-saved chart, built from real
`metrics` documents the running backend is writing every 5 minutes.
`/dashboard/reports`: if you ran `python -m reports.daily_report --demo-data` beforehand, show a full
week of summaries, download a PDF, and do a client-side CSV export live.

## 12. Settings (wrap-up)
`/dashboard/settings`: point at the deployed-model panel — mAP50, the 5 classes, and the honest
"Emergency classifier: Not trained (T4 skipped, no dataset — RFID priority used instead)" line. This is
a good place to close: "every part of this dashboard is backed by a real database document and a real
backend process — nothing here is a static mockup."

## If something doesn't come up live
Every page has a built-in empty state that names the exact command to run to populate it
(e.g. "Run `backend/emergency/ambulance_sim.py`") — read that out loud rather than improvising; it's
more convincing than pretending nothing's wrong.
