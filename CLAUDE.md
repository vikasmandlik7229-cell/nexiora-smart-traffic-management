# Smart Traffic Management System — Build Instructions for Claude (v3: Web + Trained Models)

You are helping me build a complete Smart Traffic Management System as a **college final-year project**. It is **software-only** (no physical sensors) and the user interface is a **web application** (no mobile app, no Flutter).

Hardware stand-ins:
- Cameras → recorded traffic videos (4 lanes at the main junction J1)
- Traffic lights → virtual signals (drawn on video and shown on the website)
- RFID → a virtual RFID tag ID checked against an authorised-vehicle registry
- GPS → a simulated ambulance moving along a route
- Other intersections → virtual junctions with simulated traffic counts

My laptop: Windows, NVIDIA RTX 4050 Laptop GPU (6 GB VRAM, CUDA 12.x), Python 3.12. Models are **trained locally on this GPU**.

Build **phase by phase** (section 11). After each phase, stop, tell me what you built, how to run and test it, and wait for my confirmation.

**Already done (as of Phase 12 / final integration):** All phases 1 through 12 — see section 11's Build Phases list for the authoritative, up-to-date status of each one, including what was skipped (T4/T5, no dataset) and what was found-and-fixed along the way. `backend/main.py` runs the whole backend in one process, and `README.md` / `docs/OBJECTIVES_MAP.md` / `docs/DEMO_SCRIPT.md` / `docs/VIVA_QA.md` document the finished system. `ROI_POLYGONS`/`STOP_LINES` in `config.py` now hold real calibrated per-lane coordinates, not placeholders. If my previous CLAUDE.md had accurate training details that this file lacks, keep them — see section 4.5 for what was ported over from it (saved as `CLAUDE_old.md`).

**Phase 13 (2026-10-31): migrated off Firebase entirely**, after a Firestore free-tier daily write-quota exhaustion froze the live dashboard for most of a day. The database is now a local SQLite file (`backend/db/sql_client.py`, one generic `documents` table — see section 2), login is a local JWT (`backend/db/auth.py`, PBKDF2 + PyJWT) instead of Firebase Authentication, and the website polls `backend/api/server.py`'s own JSON API (`/api/collection/{name}`, `/api/doc/{name}/{id}`, plus named write endpoints) every 2s instead of using Firestore's `onSnapshot`. No more cloud dependency, no quota, no deployment - the site runs fully locally (`npm run dev` + `python main.py`). The Firebase Hosting deployment at nexiora-traffic.web.app is retired and no longer maintained; `firebase.json`/`.firebaserc`/`backend/firebase/` (rules, old client, old seed script) are deleted.

---

## 1. Project Objectives (every feature must map to one)

1. Intelligent traffic management that monitors roads and manages signals efficiently.
2. Real-time traffic density: detect and count vehicles per lane, and adjust signal timing.
3. Adaptive signal control: longer green for busy lanes, less waiting for quiet lanes.
4. ML prediction of future congestion from historical counts and timestamps: peak hours (hourly) and short-term (next 5–10 minutes).
5. Automatic priority for **authorised** emergency vehicles (vision detection + virtual RFID authorisation).
6. Real-time ambulance tracking on a live map, coordinating upcoming signals (optimized green corridor).
7. AI red-light violation detection with recorded evidence.
8. Air-quality monitoring and eco-friendly control (reduce idling when pollution is high).
9. A modern **public web portal**: live traffic, signals, map, ambulance tracking, alerts, predictions, air quality.
10. A centralised **web controller dashboard** to monitor all intersections, watch live video, and manage emergencies and accidents.
11. Measurably reduce waiting time, idle fuel and emissions (adaptive vs fixed-time comparison).
12. Improve road safety and emergency response time.
13. Historical records and reports on traffic patterns, system performance and congestion trends.
14. Accident detection, congestion-impact prediction and automatic alternative-route suggestions.

---

## 2. Tech Stack

**Backend (Python 3.12)**
- Main runtime venv: `backend/venv`, with **CUDA-enabled PyTorch** so live detection uses the RTX 4050; automatic CPU fallback if no GPU (`DEVICE = "auto"` in config).
- Training venv: `backend/training/venv_train` (CUDA PyTorch). **Both venvs must use the same ultralytics version** so trained weights load in the runtime.
- `ultralytics` (YOLOv8 detection + classification, ByteTrack tracking), `opencv-python`, `numpy`, `pandas`
- `scikit-learn`, `joblib` (prediction), `networkx` (routes), `PyJWT` (local login tokens), `requests`, `python-dotenv`
- `matplotlib`, `reportlab` (reports), `pytest`
- `fastapi` + `uvicorn` (local API: live video stream, evidence images, report files, the JSON data API, login)

**Database:** a single local SQLite file (`backend/data/smart_traffic.db`, built by `backend/db/sql_client.py`) — no cloud dependency, no daily write quota, nothing to deploy. One generic `documents` table (`collection`, `id`, `data` JSON blob, plus `status`/`ts` columns for fast filtering/sorting) holds every "collection" from the original design (junctions, signals, live_counts, violations, ...). Login is a local JWT (`backend/db/auth.py`: PBKDF2-HMAC-SHA256 password hashing + PyJWT), not a cloud auth provider. (This replaced Firebase Firestore/Auth/Hosting in Phase 13, after a free-tier write-quota exhaustion froze the dashboard for a day — see section 11.)

**Web app (`web/`):** React 18 + Vite + Tailwind CSS, `react-router-dom`, `react-leaflet` + `leaflet` (OpenStreetMap, no API key), `recharts`, `lucide-react` icons. Plain JavaScript (no TypeScript), so it is easy to explain. Live-feeling updates come from polling the local API every 2s (`hooks/useDoc.js`/`useCollection.js`), not a cloud real-time listener.

**Air quality:** OpenWeather Air Pollution API (free key in `.env`) with a simulated fallback.

---

## 3. Folder Structure (add to the existing structure)

```
smart-traffic/
├── CLAUDE.md
├── backend/
│   ├── config.py               # ALL tunable values and assumptions
│   ├── main.py                 # runs everything
│   ├── api/server.py           # FastAPI: MJPEG stream, evidence, reports, health
│   ├── tools/roi_picker.py     # (done)
│   ├── detection/              # (done) detector.py, lane_counter.py
│   │   ├── motion_tracker.py   # per-track speed and stationary time
│   │   └── emergency_classifier.py  # crop classifier + temporal voting
│   ├── training/                # (exists) venv_train, finetune_uvh26.py, uvh26_yolo/
│   │   ├── emergency/          # emergency-vehicle classifier dataset + training
│   │   ├── accident/           # optional accident classifier
│   │   ├── evaluate_detector.py
│   │   └── reports/            # training charts and metrics for my project report
│   ├── data/models/            # deployed weights: vehicle_*.pt, emergency_cls.pt, accident_cls.pt
│   ├── signals/  controller.py, fixed_time_baseline.py, virtual_junctions.py, commands.py, display.py
│   ├── violations/red_light.py
│   ├── network/  road_graph.py, router.py
│   ├── emergency/  geo.py, authorised.py, ambulance_sim.py, green_corridor.py, corridor_evaluator.py
│   ├── accidents/  detector.py, impact.py, manager.py, accident_sim.py
│   ├── prediction/  generate_hourly_data.py, generate_minute_data.py, train_peak.py, train_short.py,
│   │                predict_peak.py, predict_short.py, data/, models/, charts/
│   ├── metrics/  wait_time.py, eco.py
│   ├── air_quality/aqi.py
│   ├── reports/  daily_report.py, output/
│   ├── firebase/  db.py, seed.py, check.py, firestore.rules
│   ├── videos/  violations_images/  accident_images/
│   └── tests/
├── web/                        # React + Vite website
└── docs/
```

---

## 4. Models and Training (local RTX 4050)

### 4.1 Vehicle detector (UVH-26 fine-tune)
- Dataset: UVH-26 (Indian traffic, COCO format, sharded image folders), already converted to YOLO format in `backend/training/uvh26_yolo/`.
- **Classes (5):** 0 car, 1 bike, 2 auto, 3 bus, 4 truck. Mapping: Hatchback, Sedan, SUV, MUV, Van → car; Two-wheeler, Bicycle → bike; Three-wheeler → auto; Bus, Mini-bus, Tempo-traveller → bus; Truck, LCV → truck; Others → dropped. (The previous conversion used 4 classes; re-convert labels only, without copying images again if possible.)
- Training: YOLOv8n first (fast, also usable on CPU laptops); optionally YOLOv8s (better small/far bikes) if time allows. imgsz 640, AMP on, batch sized to fit 6 GB VRAM (or batch=-1 auto), patience 15, ~50 epochs, Windows-safe dataloader (`if __name__ == "__main__":`, workers 2–4), no RAM caching. Always run a **smoke test** (1–2 epochs on a small subset) before the full run.
- Evaluation (`evaluate_detector.py`): mAP50, mAP50-95, precision and recall per class on UVH-26 val; compare against pretrained COCO YOLOv8n mapped to the same classes (no auto class in COCO, so report that honestly); count accuracy on my own lane videos (manual ground-truth counts on ~20 sampled frames per lane). Save charts and a markdown summary to `training/reports/`.
- Deploy: copy the chosen best.pt to `backend/data/models/vehicle_uvh26_<n|s>.pt`; set `MODEL_PATH` in config. Keep the COCO model as a fallback option.

### 4.2 Emergency-vehicle classifier (Objective 5)
- Purpose: recognise ambulances (and fire/police) in the video. Recognition alone never grants priority; it creates an **emergency request** that still needs virtual RFID authorisation (section 6.5).
- Data: emergency-vehicle images I already have from the `traffic-violation-system` repo datasets (for example Indian emergency vehicle datasets under `datasets/external/` and the repo's `ambulance_training/labels.json`). **Warning from that repo: the original dataset labels are partly wrong** (some "others" are ambulances and some "ambulance" are police). Clean them: deduplicate near-identical images (perceptual hash), and generate contact sheets so I can quickly verify or correct labels.
- Negatives: vehicle crops (car, auto, bus, truck) cut from UVH-26 using its boxes, with no emergency vehicles.
- Classes: `ambulance`, `fire`, `police`, `normal` (merge to `emergency`/`normal` if fire/police have too few images; report counts first).
- Model: YOLOv8n-cls (or yolov8s-cls) trained locally, imgsz 224, class-balanced, split by source/video where possible to avoid leakage.
- Runtime: classify crops of car/bus/truck tracks every N frames; a track is "emergency" when ≥ 3 of its last 5 classifications pass `EMERGENCY_CONF`. Report precision/recall and a confusion matrix; prefer **high precision** (few false ambulances).
- **Status: BLOCKED pending data.** No emergency/ambulance/accident dataset was found anywhere on this machine (searched `D:\Nexiora`, Downloads, Documents) — the `traffic-violation-system` GitHub repo's own `datasets/`, `outputs/`, `runs/` are gitignored, so browsing that repo on GitHub never actually downloaded its image data here. This phase cannot proceed until the dataset location is confirmed or the data is placed on disk.

### 4.3 Accident classifier (optional, Objective 14)
- Only if I have or download a CCTV accident image dataset: YOLOv8n-cls `accident`/`normal` on frames or junction crops, used as a second opinion alongside the rule-based heuristics. Without a dataset, use heuristics only and state that honestly.
- **Status: BLOCKED pending data**, same reason as 4.2 — optional, needs a Kaggle download with the user's own `kaggle.json` credentials.

### 4.4 Not needed from the reference repo
Helmet, triple riding, speed estimation, e-challan and signal-light-colour models are out of scope (our signals are virtual, so the system already knows their state). Number-plate reading is an optional bonus only after everything else works.

### 4.5 Preserved from `CLAUDE_old.md` (the pre-v3 file, kept on disk for reference)
Operational knowledge from actually running Phase 2a that this file's section 4.1 doesn't spell out — keep applying these:
- **Venv isolation is fragile**: installing `requirements-train.txt` (which pulls in `ultralytics` → `torchvision`) **silently upgraded and replaced** a working CUDA `torch==2.6.0+cu124` with a CPU-only `torch==2.14.1+cpu` from the default PyPI index, because `torchvision`'s version constraint forced a torch upgrade and nothing pinned it back to the cu124 index. Always install `torch`+`torchvision` together from the cu124 index **last**, or pin exact compatible versions in `requirements-train.txt`, and **re-verify `torch.cuda.is_available()` after any `pip install` in `venv_train`** — don't assume a working CUDA install stays working.
- **UVH-26 images are sharded**, not flat: `UVH-26-Train/data/000/`, `/001/`, … (~5000 files per shard), same for Val. Any script that touches these files must build a filename→path index by walking `data/`, never assume `images_dir / file_name` directly.
- **UVH-26 annotations are plain COCO format**, not the merged `image`+`objects` schema the HF dataset card's YAML implies (that YAML describes the `datasets`-library feature schema, not the raw JSON on disk). Real structure: top-level `images`/`annotations`/`categories` lists, `bbox` = `[x, y, width, height]` absolute pixels (confirmed via `area == width*height` on real records), category ids **1–14** with `"Others"` (plural) as the catch-all, not `"Other"`.
- **Hugging Face Buckets download via `hf sync hf://buckets/<user>/<bucket> <dest>`**, not the regular `snapshot_download()` dataset API. `hf sync` can **stall silently** — process stays alive and keeps burning CPU, but byte count stops growing with no error. If progress is flat for 10+ minutes, kill the process and re-run; it resumes from where it left off without re-downloading completed files.
- **ByteTrack tuning already applied** in `backend/detection/bytetrack_custom.yaml` for this dense-traffic, fixed-elevated-camera footage processed at a few fps (not native video fps): `track_high_thresh=0.25`, `track_low_thresh=0.1`, `new_track_thresh=0.2` (must stay below the lowest per-class confidence override or ByteTrack never starts a track for that class), `track_buffer=60`, `match_thresh=0.9`, `fuse_score=True`. The default `match_thresh=0.8` was too strict and caused ID churn/flicker on overlapping traffic. **This will need revisiting once the 5-class fine-tuned model is deployed** — the old `CLASS_CONFIDENCE_OVERRIDES = {3: 0.25}` is keyed to COCO class id 3 (bike); the new model's bike class id will be different (per the 5-class mapping in 4.1, order TBD by `data.yaml`), so this override must be re-keyed after training, not copied as-is.
- C: drive had only ~26 GB free during this work — low enough to be worth checking before any further large downloads/installs, separate from the GPU VRAM constraint.

---

## 5. Road Network (config.py)
- 6 junctions in a 2×3 grid with placeholder coordinates I can change. `J1` = main junction with the 4 real videos; J2–J6 virtual.
- Roads connect neighbours in both directions with `distance_m` (haversine) and `base_speed_kmph`.
- Every junction has approaches `north`, `east`, `south`, `west` (J1: mapped to lane1–lane4). The approach used is found from the compass bearing.
- At least 2 different routes between most junction pairs, so detours exist.

---

## 6. Feature Specifications

### 6.1 Detection & counting (done, extended)
- Use the deployed UVH-26 model (5 classes) on GPU when available.
- **PCU-weighted density:** each lane's load = Σ class count × PCU weight (config: car 1.0, bike 0.5, auto 1.0, bus 3.0, truck 3.0 — approximate; note in docs that they can be tuned using Indian road-congress guidelines). Show both raw counts and PCU.
- `motion_tracker.py`: per track ID, the last ~3 s of positions, speed in px/s, seconds stationary.

### 6.2 Adaptive signal controller (objectives 2, 3, 11)
- One `SignalController` per junction. **Only one approach green or yellow at a time** (asserted every tick).
- Green = clamp(MIN_GREEN, MAX_GREEN, BASE_GREEN + SECONDS_PER_PCU × lane PCU). Yellow = YELLOW_TIME.
- Next lane: highest PCU, but any lane waiting > MAX_WAIT goes first (no starvation). Empty lanes skipped unless starved.
- Modes: `adaptive`, `peak`, `eco`, `emergency`, `accident`, `manual` (all safety-checked).
- If a lane is predicted `high` in 5 minutes, add PREDICTION_BONUS seconds to its next green.
- A plain-English log line for every decision.

### 6.3 Fixed-time baseline & metrics (objectives 8, 11)
- A fixed-cycle controller runs on the same counts in parallel (measurement only).
- Waiting model: each second, every vehicle in a red/yellow lane adds 1 waiting vehicle-second. Average wait = waiting vehicle-seconds ÷ vehicles served.
- Idle fuel = waiting vehicle-seconds × IDLE_FUEL_L_PER_HOUR ÷ 3600; CO₂ = fuel × CO2_KG_PER_L (labelled assumptions in config, defaults 0.6 and 2.31).
- Show adaptive vs fixed on the video and publish to `metrics` every 5 minutes.

### 6.4 Red-light violations (objective 7)
Stop line per lane; violation = bottom-centre crosses the line while that lane is red (and not an emergency vehicle in emergency mode). Red box + "VIOLATION", snapshot (full frame + crop), database record, alert, each track counted once. `VIOLATION_TEST_MODE` holds one lane red for 30 s for demos.

### 6.5 Authorised emergency vehicles (objective 5)
- `authorised_vehicles` holds ambulances with a virtual RFID `tagId` (seed 3 examples).
- Emergencies start as `emergency_requests` from: the **driver web page**, the **controller dashboard**, the **simulator**, or the **camera** (emergency classifier on J1 → request with source `vision`, vehicleId unknown).
- The backend approves only with a valid vehicleId + tagId + active. Vision-only requests at J1 are handled by `VISION_EMERGENCY_POLICY` in config: `"alert_only"` (default: alert the controller, who can approve with one click) or `"auto_local"` (give priority at J1 only, never a multi-junction corridor). Rejected requests → `security` alert.
- The web app never writes `emergency/active` directly.

### 6.6 Optimized green corridor (objectives 6, 12)
- On approval, `router.py` picks the fastest route (live congestion weights, blocked roads excluded).
- Per upcoming junction: ETA = remaining distance ÷ speed; queue clearance = YELLOW_TIME + STARTUP_LOST_TIME + PCU on that approach × SECONDS_PER_QUEUED_PCU. Pre-empt when ETA ≤ clearance + SAFETY_MARGIN, so the queue is flushed before the ambulance arrives. Yellow first; at most the next 2 junctions pre-empted at once.
- After the ambulance passes (> PASS_DISTANCE beyond): recovery serves the longest-waiting lanes first.
- Reroute automatically if an accident blocks the route.
- `corridor_evaluator.py`: time saved per trip vs no corridor (from signal timelines) → `emergency_trips`; experiment mode with 20 simulated trips + chart.

### 6.7 Prediction (objective 4)
**A. Peak hours:** 30 days of synthetic hourly data + real `traffic_logs`; Linear Regression vs Random Forest (MAE, RMSE, R²); next 24 h; top 20% = peak hours → `peak` mode.
**B. Next 5/10 minutes:** 14 days of per-minute synthetic data with congestion build-ups; features lag_1…lag_10, rolling means, trend, hour_sin/cos, dayOfWeek, isWeekend, laneId; targets t+5, t+10; naive vs Linear Regression vs Random Forest with a **time-based split**; low/medium/high from LANE_CAPACITY_PCU; live every 60 s → `short_predictions` + `prediction` alerts (max once per 10 min per lane) + controller bonus.

### 6.8 Accident detection & route replanning (objective 14)
- Heuristics at J1: vehicle stationary > ACCIDENT_STOP_SECONDS while its lane is green or inside the junction area; or two tracks with IoU > COLLISION_IOU that both drop speed > 70% within 1 s. Confirm after ACCIDENT_CONFIRM_SECONDS. Optional classifier second opinion (4.3). Orange "ACCIDENT?" box + snapshot.
- Triggers for demos and camera-less roads: `accident_sim.py`, the dashboard "Report accident" button, `ACCIDENT_TEST_MODE`.
- Impact: predicted arrival rate × clearance time (by severity) − remaining capacity → predicted queue and extra delay.
- Manager: block road, `accident` mode on the approach, alternative routes for traffic through that road, alert with the best detour, reroute an active ambulance; on resolve, reopen and restore.

### 6.9 Air quality & eco mode (objective 8)
AQI per junction every AQI_REFRESH_MINUTES (simulated fallback), `air_quality` + `air_quality_logs`; AQI ≥ 4 → `eco` mode (lower MAX_WAIT, shorter cycles) + `air` alert at most once per hour.

### 6.10 Reports (objective 13)
`daily_report.py --date` / `--range`: aggregate everything → `daily_reports/{date}` + a professional PDF (charts with captions) + CSV files in `reports/output/`. A `--demo-data` option fills one past week of realistic records (within the write budget).

### 6.11 Local API (`backend/api/server.py`, FastAPI on port 8000)
- `GET /api/health` — module status.
- `GET /api/stream/j1` — **MJPEG live stream** of the annotated J1 video (2×2 grid or single lane via `?lane=`), ~10–15 fps, JPEG quality configurable.
- `GET /api/evidence/violations/{file}`, `/api/evidence/accidents/{file}` — evidence images.
- `GET /api/reports` and `/api/reports/{file}` — list and download PDF/CSV reports.
- `POST /api/auth/login`, `GET /api/auth/me` — local login (`db/auth.py`: PBKDF2 + JWT), replacing Firebase Authentication.
- `GET /api/collection/{name}`, `GET /api/doc/{name}/{id}` — generic JSON reads, polled every 2s by the website (replaces Firestore's `onSnapshot`); `POST /api/commands`, `POST /api/accident-reports`, `PATCH /api/accidents/{id}/resolve`, `POST /api/emergency-requests`, `PUT /api/trip-control/{vehicleId}`, `PUT /api/authorised-vehicles/{vehicleId}` — named writes, one per website write action.
- Protected endpoints require a locally-issued JWT (`Authorization: Bearer` header, or `?token=` for `<img>` tags), role-checked per collection/endpoint (a direct, auditable port of the old `firestore.rules` table). The stream allows public view of the annotated traffic only if `PUBLIC_STREAM = True`.
- CORS for `http://localhost:5173` (the site runs locally; no hosted domain anymore).
- Runs inside `main.py` in a background thread; the video pipeline shares the latest annotated frame through a thread-safe buffer.

### 6.12 Website (objectives 9, 10) — React + Vite + Tailwind
**Design:** modern command-centre look, dark default + light toggle, one accent colour, signal colours red #E53935 / amber #FFB300 / green #43A047, rounded cards, consistent spacing, responsive (desktop first, usable on mobile browsers), skeleton loaders, empty and error states, live data polled every 2s from the local API (no hard-coded data). A banner shows "Backend offline" when `/api/health` fails.

**Public portal (no login):**
1. **Live Overview** — totals, current modes, congestion per junction, AQI badge, ambulance/accident banners, latest public alerts.
2. **Signals** — junction selector; animated traffic lights with countdown from `phaseEndsAt`; PCU and counts.
3. **City Map** — junctions coloured by congestion, roads by status, live ambulance with route, accidents, detours in green, legend.
4. **Predictions** — next 5/10 minutes per lane, 24 h chart with peak hours.
5. **Air Quality** — AQI per junction, pollutants, 24 h trend, eco-mode status.
6. **Alerts** — public alerts (ambulance, accident, congestion, prediction, air).

**Ambulance driver page (login, role `driver`):** choose vehicle + enter tag ID → destination → "Start Emergency Trip" → pending/approved (route, ETA, live map, pre-empted junctions)/rejected (reason) → "End trip".

**Controller dashboard (login, role `controller`, sidebar layout):**
1. **Command Centre** — KPIs (vehicles now, avg wait adaptive vs fixed, active emergencies, active accidents, violations today, AQI), **live J1 video**, junction grid with mini signals, live alert feed, pending vision emergency requests with Approve/Reject.
2. **Junction Detail** — live video (J1), lane counts/PCU charts, predictions, mode, **manual override** (force green ≤ MAX_OVERRIDE_SECONDS / release, via `commands`; shows done/rejected).
3. **City Map** (full features + side panel).
4. **Emergencies** — start an emergency, active trip panel, trip history with time saved, average time-saved chart.
5. **Accidents** — report an accident, active/resolved, impact, detours on a mini map, evidence image, "Mark resolved".
6. **Violations** — filterable table, evidence images (via the local API with token), charts by lane and hour.
7. **Predictions**, 8. **Performance** (adaptive vs fixed, fuel, CO₂ over 7 days), 9. **Air Quality**.
10. **Reports** — daily summaries and charts, trend chart, download PDF/CSV from the local API, client-side CSV export.
11. **Settings** — authorised vehicles (add/deactivate/edit tag), users and roles, model info (which detector/classifier is deployed, with their metrics).

**Access rules (enforced in `backend/api/server.py`, not a separate rules file):** public read for display collections; `violations`, `emergency_requests`, `commands`, `authorised_vehicles`, `users` readable by controllers only (drivers can read their own requests); `emergency_requests` writable by driver/controller; `commands`, `authorised_vehicles`, accident resolve and user roles writable by controller only. The Python backend's own database access always bypasses these checks (they only gate the website's HTTP requests).

---

## 7. Data Model

Each "collection"/"doc" below is a logical grouping, physically stored as rows in the single `documents` table in `backend/data/smart_traffic.db` (`collection`, `id`, `data` JSON blob — see `backend/db/sql_client.py`), the same shape Firestore used before Phase 13's migration.

| Collection / Doc | Fields |
|---|---|
| `junctions/{id}` | name, lat, lng, isVirtual, approaches {laneId: bearing} |
| `roads/{id}` | from, to, distanceM, baseTimeS, status: open\|congested\|blocked, congestionFactor |
| `signals/{junctionId}` | lanes {laneId: {state, count, pcu}}, activeLane, phase, phaseEndsAt, mode, updatedAt |
| `live_counts/{junctionId}` | lanes {laneId: {count, pcu, byClass}}, updatedAt |
| `traffic_logs/{autoId}` | junctionId, minute, lanes {laneId: {avgCount, avgPcu}}, hour, dayOfWeek |
| `predictions/{junctionId}` | hourly, peakHours, model, mae, r2, updatedAt |
| `short_predictions/{junctionId}` | lanes {laneId: {now, in5, in10, level}}, model, generatedAt |
| `authorised_vehicles/{vehicleId}` | type, tagId, hospital, driverName, active |
| `emergency_requests/{autoId}` | vehicleId, tagId, destinationJunction, source: web\|dashboard\|sim\|vision, requestedBy, status, reason, visionConfidence |
| `emergency/active` | active, vehicleId, lat, lng, speedKmph, routeJunctions, routePolyline, nextJunctionId, etaNextS, preempted, startedAt |
| `emergency_trips/{autoId}` | vehicleId, startedAt, endedAt, travelTimeS, estimatedWithoutCorridorS, timeSavedS, junctionsPreempted, rerouted |
| `accidents/{id}` | junctionId, roadId, laneId, lat, lng, method: vision\|manual\|sim, severity, status, detectedAt, resolvedAt, predictedQueue, predictedDelayMin, alternativeRoutes, imageFile |
| `alerts/{autoId}` | type, severity, public (bool), message, junctionId, timestamp, read |
| `violations/{autoId}` | junctionId, laneId, trackId, vehicleType, imageFile, cropFile, timestamp |
| `air_quality/{junctionId}`, `air_quality_logs/{autoId}` | aqi, label, pm2_5, pm10, no2, co, source, timestamp |
| `metrics/{junctionId}_{date}` | avgWaitAdaptiveS, avgWaitFixedS, waitReductionPct, idleVehicleSecondsSaved, fuelSavedL, co2SavedKg, updatedAt |
| `daily_reports/{date}` | summary fields, pdfFile, csvFiles |
| `commands/{autoId}` | junctionId, type, laneId, durationS, requestedBy, status, reason |
| `users/{uid}` | name, email, role: controller\|driver\|viewer, vehicleId (drivers) |
| `system/models` | detector name, classes, mAP50, emergency classifier precision/recall, updatedAt |

**Write cadence** (no quota to respect anymore since Phase 13's SQLite migration, but still sensible not to write pointlessly often): signals only on phase change (the website computes countdowns); live_counts every 15 s; traffic_logs one doc per junction per minute; short_predictions every 60 s; metrics every 5 min; emergency/active every 1 s only during a trip. Batched background write queue (`backend/db/sql_client.py`'s single writer thread). Website pages poll every 2s and only while the page is visible/mounted, using `limit()`/`orderBy()` from `web/src/lib/query.js`.

---

## 8. Rules for How You Work
- Follow the phases in order; stop after each and wait for "continue" — **unless I've explicitly said to work autonomously for a stretch of time, in which case keep going through multiple phases and compile a report for when I'm back, instead of blocking.**
- At the end of each phase: files created/changed, exact Windows PowerShell commands (`backend\venv` for runtime, `backend\training\venv_train` for training, `web` with npm), what I should see, and a 4–5 line viva explanation.
- Run commands and tests yourself where possible; tell me only what I must do by hand (clicking, accounts, keys, label checking).
- Long training runs: start them in the background with logs written to a file, tell me how to monitor progress, and let us continue other phases meanwhile.
- All tunable values and assumptions in `config.py`; secrets in `.env` (git-ignored). Never ask me to paste tokens or keys into chat.
- Clean, commented, simple code with a header comment in every file.
- Degrade gracefully (no video, GPU, or database → clear message, keep running where possible).
- Free tools and tiers only.
- Check free disk space before creating large files and tell me if it is low.
- Ask before guessing if something is unclear — except during an explicitly-declared autonomous stretch, where you make the reasonable call, document it, and move on instead of stopping.

---

## 9. Safety Rules (never break)
1. Only one approach per junction is green or yellow at any time.
2. Green always passes through yellow before red (including pre-emption and overrides).
3. Manual overrides ≤ MAX_OVERRIDE_SECONDS and can be rejected.
4. Only authorised vehicles get a multi-junction green corridor; vision detection alone never does.

---

## 10. Honesty Rules for the Report
State clearly which parts are simulated (virtual signals, GPS, RFID, virtual junctions, synthetic history data) and which use real data (videos, UVH-26, emergency-vehicle images). Report real measured metrics only; never invent numbers.

---

## 11. Build Phases
1. Setup *(done)*
2. Detection & lane counting *(done — `config.py`'s `ROI_POLYGONS`/`STOP_LINES` now hold real calibrated per-lane pixel coordinates, not placeholders)*
2a. UVH-26 download, inspection and conversion *(done, 5-class)*
T1. Audit + environment alignment *(done)*
T2. Train vehicle detector *(done — YOLOv8n, 5 classes)*
T3. Evaluate, compare with COCO, deploy into the pipeline, PCU counting *(done — mAP50 0.901 overall; per-class breakdown in `training/reports/DETECTOR_RESULTS.md`; see README's "Known gap" note on the never-filled-in manual count-check sheet)*
T4. Emergency-vehicle classifier *(skipped — no dataset found, see 4.2; RFID-only priority is the shipped mechanism for objective 5, not a stand-in)*
T5. *(optional)* Accident classifier *(skipped — no dataset found, see 4.3; heuristics-only, stated honestly in Settings' model-info panel)*
3. Adaptive signal controller + fixed-time baseline + metrics *(done, 52 pytest tests)*
4. Firebase (budget-aware), road network seed, virtual junctions, commands, local API server *(done)*
5. Red-light violation detection *(done — evidence capture + Firestore write fixed during Phase 12 integration, was previously discarded)*
6. Authorised emergencies, router, optimized green corridor, evaluation *(done — green-corridor bearing and corridor-evaluator lead-time bugs fixed)*
7. Prediction: peak hours + next 5/10 minutes *(done — both now publish to Firestore automatically: peak hourly via `main.py`, short-term every 60s from live J1 counts)*
8. Accident detection, impact prediction, route replanning *(done — resolve/report listeners now actually started, vision-triggered lane-blocking bug fixed)*
9. Air quality + eco mode + metrics publishing *(done)*
10. Historical records & reports *(done)*
11. Website (React 19 + Vite + Tailwind v4): setup/auth/layout → public portal → map → controller dashboard → emergencies/accidents/driver → analytics/reports/settings → polish + deploy *(done — was deployed at https://nexiora-traffic.web.app; retired in Phase 13, runs locally now)*
12. Final integration (`backend/main.py`), documentation (`README.md`, `docs/OBJECTIVES_MAP.md`, `docs/DEMO_SCRIPT.md`, `docs/VIVA_QA.md`), final test review *(done)*
13. Migrate off Firebase to a local SQLite database + local JWT login *(done — see section 2 and the Phase 13 note above; no more cloud dependency or write quota; 72 pytest tests, full live end-to-end verification via curl and a real main.py run)*
