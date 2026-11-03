# Objectives Map

Maps each objective from `CLAUDE.md` §1 to the code that implements it, with an honest real/simulated
split. Written for the project report and viva — every claim here points at a real file or a real,
reproducible command.

## 1. Intelligent traffic management that monitors roads and manages signals efficiently
`backend/signals/controller.py` (`SignalController`) + `backend/run_signals.py` (the J1 pipeline) +
`backend/signals/virtual_junctions.py` (J2–J4). Monitoring = real YOLOv8n detection on J1's 4 real
videos; management = the adaptive controller described in objective 3.

## 2. Real-time traffic density: detect and count vehicles per lane, adjust signal timing
`backend/detection/detector.py` + `backend/detection/lane_counter.py` (real detection/counting on J1) →
PCU-weighted load → `SignalController.tick(loads)` adjusts green time every cycle (§6.2 of CLAUDE.md).
PCU weights: `config.PCU_WEIGHTS`.

## 3. Adaptive signal control: longer green for busy lanes, less waiting for quiet lanes
`backend/signals/controller.py`: `green = clamp(MIN_GREEN, MAX_GREEN, BASE_GREEN + SECONDS_PER_PCU * load)`,
next-lane selection by highest PCU with a `MAX_WAIT` no-starvation guarantee. Verified by
`backend/tests/test_controller.py` (10 tests, fake-clock based). Modes: adaptive/peak/eco/emergency/
accident/manual, all going through the same safety-checked `tick()`.

## 4. ML prediction of future congestion (peak hours + next 5–10 minutes)
**Peak hours**: `backend/prediction/train_peak.py` (Linear Regression vs Random Forest, MAE/RMSE/R²) on
30 days of synthetic hourly data + real `traffic_logs`; `predict_peak.py` predicts the next 24h, flags
the top 20% as peak, publishes to the database `predictions/{junctionId}` — now running automatically every
hour inside `main.py` (`prediction.predict_peak.start_background`).
**Short-term**: `train_short.py` on 14 days of synthetic per-minute data with engineered lag/rolling/
cyclical features, time-based train/test split; `predict_short.py`'s `RollingBuffer` is now fed real
per-minute counts from J1's live pipeline (`run_signals.py`, wired in Phase 12) and publishes to
`short_predictions/J1` every 60 seconds. Web: `Predictions.jsx` (public) and its dashboard reuse.

## 5. Automatic priority for authorised emergency vehicles (vision + virtual RFID)
**As actually built**: RFID-only. `backend/emergency/authorised.py` validates `vehicleId` + `tagId`
against `authorised_vehicles` (the local database) before ever creating `emergency/active` or pre-empting a
signal — this is Safety Rule 4 (`CLAUDE.md` §9) and is enforced in code, not just policy.
Vision-based emergency-vehicle detection (T4) was explicitly skipped — no usable dataset was ever found
on this machine (`CLAUDE.md` §4.2) — so there is no camera-triggered emergency path and no human-approval
UI for one; the Command Centre's "recent emergency requests" panel is read-only for exactly this reason
(see `docs/VIVA_QA.md` for how to explain this honestly if asked).

## 6. Real-time ambulance tracking on a live map, coordinating upcoming signals
`backend/emergency/ambulance_sim.py` (the GPS stand-in) writes `emergency/active` every second;
`backend/emergency/green_corridor.py` pre-empts up to `MAX_PREEMPTED_JUNCTIONS` (2) upcoming junctions
using ETA-vs-queue-clearance math (`CLAUDE.md` §6.6), always yellow-before-red (Safety Rule 2). Web:
`components/CityMap.jsx` (shared by the public map, dashboard map, Emergencies page and the driver
portal) renders the live ambulance marker + route + pre-empted junctions. Time-saved evaluation:
`emergency/corridor_evaluator.py` (offline, 20 paired simulated trials, +122.1s average measured this
session after fixing a lead-time bug — see `CLAUDE.md`'s "Errors and fixes" history).

## 7. AI red-light violation detection with recorded evidence
`backend/violations/red_light.py`: stop-line-crossing detection + full-frame and cropped evidence
images, on real J1 footage. **Found and fixed during Phase 12 integration**: the detector's return value
was being silently discarded in `run_signals.py` — violations were detected and evidence saved to disk,
but never written to the database. Now wired to `db_client.add_violation(...)` + a controller alert; verified
end-to-end during this session's smoke test (real violation documents observed in the database with the
exact fields the dashboard reads). Web: `dashboard/Violations.jsx` (filters, by-lane/by-hour charts,
expandable evidence images).

## 8. Air-quality monitoring and eco-friendly control
`backend/airquality/aqi.py`: OpenWeather Air Pollution API with a clearly-labelled simulated fallback
(`source: "live"|"simulated"` on every `air_quality` doc); `EcoModeManager` switches a junction to eco
mode at AQI ≥ 4 (shorter cycles, lower `MAX_WAIT`). Polled for **all** configured junctions every
`AIR_QUALITY_REFRESH_INTERVAL` from inside the J1 pipeline. Web: `AirQuality.jsx` (reused by both public
and dashboard routes — identical public-read data, nothing controller-specific to add).

## 9. A modern public web portal
`web/src/pages/public/*`: Live Overview, Signals, City Map, Predictions, Air Quality, Alerts — all on
live data polled from the local API every 2s (no hard-coded data), dark/light theme, skeleton/empty/error states, a
"Backend offline" banner driven by `/api/health`. Runs locally (no deployment - see CLAUDE.md Phase 13).

## 10. A centralised web controller dashboard
`web/src/pages/dashboard/*`: Command Centre (KPIs, live J1 video, junction grid, alert feed), Junction
Detail (per-lane charts, manual override via `commands`), City Map, Emergencies, Accidents, Violations,
Predictions, Performance, Air Quality, Reports, Settings (authorised-vehicle management, users/roles,
deployed-model info). Manual override and "mark resolved"/"report accident" write real database
documents that real backend listeners process — not static buttons (two real access-control gaps
found and fixed while building this: accidents resolve was unconditionally blocked, and
`authorised_vehicles` had no write path at all for Settings).

## 11. Measurably reduce waiting time, idle fuel and emissions (adaptive vs fixed-time)
`backend/signals/fixed_time_baseline.py` runs in parallel on the same counts (measurement only, never
controls real lights); `backend/metrics/wait_time.py` + `eco.py` compute the comparison every second,
published to the database every `FIRESTORE_METRICS_WRITE_INTERVAL` (5 min). Web: `dashboard/Performance.jsx`
(7-day trend, real `metrics` documents only — no invented numbers). Config assumptions
(`IDLE_FUEL_L_PER_HOUR`, `CO2_KG_PER_L`) are explicitly labelled as tunable estimates in `config.py`.

## 12. Improve road safety and emergency response time
Safety Rules 1–4 (`CLAUDE.md` §9), enforced in `SignalController` and asserted by
`backend/tests/test_controller.py`: single green/yellow per junction at any time; yellow always before
red, including pre-emption and manual override; overrides capped at `MAX_OVERRIDE_SECONDS`; only
RFID-authorised vehicles ever get a multi-junction corridor.

## 13. Historical records and reports
`backend/reports/daily_report.py`: aggregates `metrics`/`violations`/`emergency_trips`/`accidents`/
`air_quality_logs` for a date or range into `daily_reports/{label}` (the local database) + a PDF (ReportLab,
with captioned matplotlib charts) + CSVs on disk, served by the local API. Web: `dashboard/Reports.jsx`
(trend chart, per-report summaries, PDF/CSV download links, client-side CSV export of any summary).

## 14. Accident detection, congestion-impact prediction, automatic alternative routes
`backend/accidents/detector.py` (stationary-while-green + collision-via-IoU-and-speed-drop heuristics,
with a frozen-baseline-speed bug fixed this session), `accidents/impact.py` (predicted queue/delay),
`accidents/manager.py` (blocks the road, computes a detour via `network/router.py` which already
excludes blocked roads, alerts publicly, reroutes an active ambulance if its route is affected).
**Found and fixed during Phase 12 integration**: the resolve/report listeners existed but were never
started by anything, and the vision-triggered call never actually passed its `controllers` dict (so
lane-blocking silently never fired) — both fixed and wired into `main.py`. No accident-image classifier
exists (T5 skipped, same reason as T4); heuristics-only, stated honestly in both `CLAUDE.md` and the
Settings page's model-info panel.
