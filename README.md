# Nexiora — Smart Traffic Management System

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-local%20API-009688?logo=fastapi&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-fine--tuned-00FFFF?logo=yolo&logoColor=black)
![License](https://img.shields.io/badge/license-MIT-green)

A software-only, final-year capstone project: adaptive traffic-signal control, red-light violation
detection, authorised-ambulance priority routing, accident detection, air-quality-aware "eco mode",
short/long-term congestion prediction, and a full web portal + controller dashboard — all backed by a
real fine-tuned vehicle detector running on 4 real traffic videos at junction **J1**, with 3 further
junctions (**J2–J4**) simulated.

Runs fully locally — no cloud dependency, no deployment, no usage quota (migrated off Firebase to a
local SQLite database + local JWT login in Phase 13; see `CLAUDE.md` for why).
Full build log and phase-by-phase spec: see `CLAUDE.md`.

> **This repository ships source code only.** Trained model weights, the UVH-26 training dataset, the
> local SQLite database, captured video footage/evidence images, and `.env` secrets are all intentionally
> excluded (see `.gitignore`) — they're either large binary artifacts, third-party dataset-licensed data,
> or local runtime state, none of which belong in source control. See
> [Weights & data — not included](#weights--data--not-included) for how to reproduce them.

## What's real vs simulated

| Real | Simulated |
|---|---|
| Vehicle detection (fine-tuned YOLOv8n, 5 classes, UVH-26 dataset) on 4 real lane videos at J1 | Junctions J2–J4 (no camera — randomised plausible loads) |
| Adaptive signal control, fixed-time baseline, wait/fuel/CO₂ metrics | Traffic lights (drawn, not physical hardware) |
| Red-light violation detection + evidence capture, on real footage | RFID (a virtual tag ID checked against a database registry) |
| Local SQLite backend + local JWT login (no cloud service) | GPS (an ambulance's position is interpolated along a route, not read from a real device) |
| Accident detection heuristics (stationary-while-green, collision via IoU+speed-drop) on real footage | Historical traffic data used for prediction model training (synthetic, generated to have realistic daily/weekly patterns) |
| Adaptive-vs-fixed comparison, green-corridor pre-emption logic, route-finding over the road graph | Accidents on J2–J4 and the demo "Report accident" / `accident_sim.py` paths |
| Peak-hour and short-term (5/10 min) prediction models, trained and evaluated on real + synthetic data | — |

**Explicitly descoped** (see `CLAUDE.md` §4.2/4.4, T4/T5): a vision-based emergency-vehicle classifier and
an accident-image classifier were never trained — no usable dataset was ever found on this machine. Ambulance
priority is **RFID-only** (vehicleId + tag checked against `authorised_vehicles`), which is the system's actual
objective-5 mechanism, not a fallback.

## Architecture

```
backend/   Python 3.12 — detection, signal control, prediction, SQLite database, FastAPI local API
web/       React 19 + Vite + Tailwind v4 — public portal, controller dashboard, driver portal
```

Everything lives on the one machine running `backend/main.py`: a single SQLite file
(`backend/data/smart_traffic.db`, via `backend/db/sql_client.py`) is both the Python backend's data
store and the thing the website reads. The website never touches the database file directly — it talks
to `backend/api/server.py` (FastAPI, port 8000) over plain HTTP, polling a small generic JSON API
(`/api/collection/{name}`, `/api/doc/{name}/{id}`) every 2 seconds to get the "live" feel Firestore's
real-time listeners used to provide, plus a handful of named write endpoints and a local login
(`/api/auth/login`, JWT-based) replacing Firebase Authentication. The same local server also serves the
live video stream and evidence-image downloads — the only piece of this system not reachable from the
public internet by design (traffic data stays on the demo PC, never uploaded anywhere).

## Running everything

### One-time setup
```powershell
# Backend runtime venv (CUDA PyTorch if you have an NVIDIA GPU, CPU fallback otherwise)
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Web app
cd ..\web
npm install
copy .env.local.example .env.local   # already filled in on this machine - see "Demo accounts" below
```

### Run the backend (one process does it all)
```powershell
cd backend
venv\Scripts\activate
python main.py                               # shows the J1 video window
python main.py --no-display                  # headless
```
This single command starts: the J1 detection/signal/violation/accident/emergency-corridor pipeline,
the simulated J2–J4 junctions, the local FastAPI server (port 8000), and the hourly peak-prediction loop.
`emergency/authorised.py`'s RFID-validation listener and `accidents/manager.py`'s report/resolve
listeners start automatically inside the J1 pipeline.

**Separate processes you run by hand**, because they stand in for independent real-world actors rather
than being part of the always-on junction loop:
```powershell
# Simulate an ambulance's GPS trip (after approving via the driver portal or this script itself)
python -m emergency.ambulance_sim --vehicle AMB001 --tag RFID-AMB-001 --to J4

# Manually trigger/resolve an accident for a demo (vision detection at J1 does this automatically)
python -m accidents.accident_sim --road J1_J2 --severity high
python -m accidents.accident_sim --resolve <accident_id> --road J1_J2

# Generate a daily/weekly report
python -m reports.daily_report --date 2026-10-29
python -m reports.daily_report --demo-data        # fills a realistic past week

# Re-seed the database (junctions, roads, authorised vehicles, system/models, demo users)
# or change a user's role - safe to re-run any time, it's an upsert.
python -m db.seed
python -m db.seed --set-role someone@example.com controller somepassword

# Quick sanity check: dump what's in the local database
python -m db.check

# Green-corridor time-saved experiment (20 paired simulated trials + a chart)
python -m emergency.corridor_evaluator --trials 20

# Backend test suite (72 tests)
pytest tests/ -q
```

### Run the website locally
```powershell
cd web
npm run dev        # http://localhost:5173, talks to the local backend on :8000
npm run build       # production build -> web/dist (still local-only; nowhere to deploy it to anymore)
```

## Demo accounts

| Role | Email | Password | Notes |
|---|---|---|---|
| Controller | `controller@nexiora.demo` | `Nexiora#Ctrl2026` | Full dashboard access |
| Driver | `driver@nexiora.demo` | `Nexiora#Drive2026` | Linked to vehicle `AMB001` |

Seeded authorised vehicles (RFID registry): `AMB001` / `RFID-AMB-001`, `AMB002` / `RFID-AMB-002`,
`FIRE001` / `RFID-FIRE-001`.

**Change these passwords before handing this project to anyone else**:
`python -m db.seed --set-role <email> <role> <newpassword>`.

## Detector performance (real numbers, not invented)

Fine-tuned YOLOv8n (5 classes: car, bike, auto, bus, truck) vs stock COCO YOLOv8n, evaluated on the
UVH-26 validation set (`backend/training/reports/DETECTOR_RESULTS.md`):

| Class | Fine-tuned mAP50 | COCO mAP50 |
|---|---|---|
| car | 0.890 | 0.594 |
| bike | 0.830 | 0.092 |
| auto | 0.861 | N/A (no matching COCO class) |
| bus | 0.760 | 0.316 |
| truck | 0.770 | 0.219 |

Ultralytics' own validator reports an overall mAP50 of 0.901 for the fine-tuned model (shown in the
Settings page, from `system/models`) — a different, less strict methodology than the from-scratch
per-class script above, so the two numbers aren't directly comparable; both are reported rather than
picking one.

**Known gap, stated honestly**: `backend/training/reports/count_check_sheet.csv` is a template for
manually counting ~20 real frames per lane to sanity-check detector accuracy against ground truth —
the `true_count` column was never filled in, so that specific manual verification step is still
outstanding. Everything else in the table above comes from the UVH-26 validation set, which matches
the model's training distribution by construction.

## Weights & data — not included

| What | Why it's excluded | How to get it |
|---|---|---|
| `backend/data/models/*.pt` — fine-tuned YOLOv8n detector, emergency-vehicle classifier probe, plate detector | Trained binary weights don't belong in git; the emergency/plate models were adopted from a third-party repo and aren't mine to redistribute (see their `SOURCE.md` files) | Train your own with `backend/training/finetune_uvh26.py` on UVH-26, or point `config.MODEL_PATH` at a stock Ultralytics checkpoint |
| `backend/training/uvh26_data/`, `uvh26_yolo/` — UVH-26 dataset (raw + YOLO-converted) | ~170 GB, third-party Indian-traffic dataset, not mine to redistribute | Download UVH-26 yourself and run the conversion scripts in `backend/training/` |
| `backend/videos/*.mp4` — real junction footage | Large (~0.8 GB) and not needed to read the code | Supply your own 4 lane videos, or run against `config.MODEL_PATH`'s stock detector on any traffic clip |
| `backend/data/smart_traffic.db` | Generated at runtime, demo data only | `python -m db.seed` (re)creates it from scratch |
| `backend/.env`, `web/.env.local` | Secrets/local config | Copy the `.example` files next to them and fill in your own keys |

## Known limitations

- Only 4 junctions are configured (`config.JUNCTIONS` = J1–J4), not the originally-planned 6-junction grid.
- Accident evidence images (`imageFile` on an `accidents` doc) are never captured by the vision
  pipeline — the dashboard's evidence slot gracefully shows "no evidence image" rather than fake data.
- "Time saved per ambulance trip" is an estimate derived from `GreenCorridor`'s real pre-emption
  decisions (the queue-clearance time credited each time it actually held a junction), not a measurement
  of an actual second, corridor-free run of the same trip — a true with/without comparison on identical
  traffic only exists via the offline `emergency.corridor_evaluator` experiment.
- Eco mode only auto-applies to J1's real `SignalController` (it runs in the same process); the
  simulated J2–J4 controllers run in a separate thread and aren't eco-adjusted.
- Access control (~15 collections, by role) is enforced in `backend/api/server.py`, not a separate rules
  file — see its `_CONTROLLER_ONLY_COLLECTIONS`/`_PUBLIC_COLLECTIONS` and the named write endpoints for
  exactly what each role can read/write.

## Tests

```
backend: 72 passed (pytest tests/)
web:     npm run build — 0 errors
```

## License

[MIT](LICENSE) — the code in this repository. Third-party model weights, datasets, and assets referenced
above remain under their own original licenses and are not redistributed here.
