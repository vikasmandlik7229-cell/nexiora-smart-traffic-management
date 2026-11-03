# Nexiora — Smart Traffic Management System

## 1. Project Overview

Nexiora is a college capstone project that simulates an AI-driven smart
traffic management system for a small road network (3–4 junctions, 4 lanes
each). A Python backend watches recorded traffic video per lane, counts
vehicles with YOLOv8, and uses an adaptive algorithm (not a fixed timer) to
decide how long each lane's green light should last. It also detects
stop-line violations, gives ambulances a green-light corridor as they
approach, and tracks local air quality. All of this is pushed to Firebase in
real time and visualized in a Flutter dashboard app.

Everything runs on recorded/sample video, not live cameras, and the
inference/demo pipeline is designed to run on a normal laptop (no GPU
required). The current dev machine happens to also have a discrete GPU
(NVIDIA RTX 4050 Laptop, 6 GB VRAM), which Phase 2a uses locally for
fine-tuning only — see section 8a. The project still doesn't *require* a
GPU to run; it's used opportunistically where available.

## 2. Goals & Scope

In scope (achievable on a college timeline, CPU-only laptop):
- Vehicle detection/counting from pre-recorded lane videos using YOLOv8n.
- Density-based adaptive signal timing (not full city-scale SCATS/SCOOT).
- Stop-line violation capture (image + timestamp) during red phase.
- A small scikit-learn congestion classifier (low/medium/high) used as a
  secondary signal, not a replacement for the rule-based timing engine.
- Firebase (Firestore) as the real-time data layer.
- Simulated ambulance GPS progress along a fixed route with signal
  preemption at nearby junctions.
- Air Quality Index per junction via the OpenWeatherMap Air Pollution API.
- A Flutter dashboard consuming all of the above.
- A fine-tuned YOLOv8n vehicle detector, trained locally on the dev
  laptop's GPU (RTX 4050, 6 GB VRAM) from the custom `UVH-26` dataset
  (Hugging Face Bucket, ~90 GB, 21,351 train / 5,299 val items), to
  improve on stock COCO weights for this project's elevated-camera,
  dense-traffic footage. Training uses a separate CUDA-enabled venv;
  inference keeps using the main CPU-only venv, same as before. See
  section 8a. A Colab notebook (`backend/training/uvh26_finetune.ipynb`)
  is kept as a fallback for running this on a GPU-less machine.

Out of scope (too heavy for this hardware/timeline):
- Live camera ingestion, multi-GPU training, training YOLO from scratch.
- Training on anything other than the single local/cloud GPU already
  covered by Phase 2a — no distributed/multi-node training.
- Real GPS hardware integration (ambulance movement is simulated).
- City-scale routing/optimization — this models one corridor of junctions.

## 3. Folder Structure

```
Nexiora Smart Traffic Management/
├── CLAUDE.md
├── README.md
├── .gitignore
├── backend/
│   ├── __init__.py
│   ├── config.py                 # every tunable setting, see section 5
│   ├── main.py                   # orchestrator (added in Phase 10)
│   ├── requirements.txt
│   ├── .env.example
│   ├── videos/                    # lane1.mp4 … lane4.mp4 (gitignored)
│   ├── tools/
│   │   └── roi_picker.py         # Phase 2 — interactive ROI/stop-line calibration
│   ├── training/                 # Phase 2a — separate CUDA venv, not the main one
│   │   ├── finetune_uvh26.py     # primary path: local RTX 4050 GPU, step-by-step CLI
│   │   ├── requirements-train.txt
│   │   └── uvh26_finetune.ipynb  # fallback: same workflow, for a GPU-less machine
│   ├── detection/                # Phase 2 — YOLO vehicle detection per lane
│   │   ├── __init__.py
│   │   ├── detector.py
│   │   └── lane_counter.py
│   ├── signal_control/           # Phase 4 — adaptive green-time engine
│   │   └── __init__.py
│   ├── violations/                # Phase 3 — stop-line violation capture
│   │   └── __init__.py
│   ├── ml/                       # Phase 5 — congestion classifier (sklearn)
│   │   └── __init__.py
│   ├── firebase/                 # Phase 6 — Firestore read/write layer
│   │   └── __init__.py
│   ├── ambulance/                # Phase 7 — corridor preemption
│   │   └── __init__.py
│   ├── airquality/                # Phase 8 — OpenWeatherMap AQI polling
│   │   └── __init__.py
│   ├── utils/                    # shared helpers (geometry, logging, etc.)
│   │   └── __init__.py
│   └── data/
│       ├── violations_images/     # captured snapshots (gitignored)
│       └── models/                # yolov8n.pt, *.joblib (gitignored)
└── frontend/                      # Flutter app, scaffolded in Phase 9
    └── README.md
```

## 4. Tech Stack

**Python (backend)**
- `ultralytics` — YOLOv8 vehicle detection (uses the pretrained `yolov8n.pt`
  COCO weights; no custom training on this hardware).
- `opencv-python` — video I/O, ROI drawing, stop-line geometry.
- `numpy`, `pandas` — array/data handling for counts and feature tables.
- `scikit-learn`, `joblib` — small congestion classifier + persistence.
- `matplotlib` — debug plots/overlays during development.
- `firebase-admin` — server-side Firestore access.
- `requests` — OpenWeatherMap API calls.
- `python-dotenv` — load `.env` secrets into `config.py`.

**Firebase**
- **Firestore** — primary real-time data store (signal states, vehicle
  counts, violations metadata, AQI readings, ambulance position).
- **Firebase Storage** (optional, Phase 3/6) — hosting violation images if
  you don't want to keep them local-only for the demo.
- Spark (free) plan is sufficient for a college-scale demo — see section 8
  for quota caveats.

**Flutter (frontend)**
- `firebase_core`, `cloud_firestore` — live data binding.
- `flutter_map` + OpenStreetMap tiles (preferred over `google_maps_flutter`
  to avoid needing a billed Google Cloud account for a student project).
- `fl_chart` — vehicle count / AQI charts.
- `provider` — state management.
- `cached_network_image` — violation image thumbnails.
- `intl` — timestamp formatting.

## 5. Configuration Reference (`backend/config.py`)

Every tunable lives in one file, each with an inline comment:
- `LANE_VIDEOS` — path to the lane1–lane4 video files.
- `YOLO_MODEL_NAME`, `CONFIDENCE_THRESHOLD`, `VEHICLE_CLASS_IDS` — detection.
- `ROI_POLYGONS`, `STOP_LINES` — per-lane geometry (placeholders until
  calibrated against real footage).
- `MIN_GREEN`, `MAX_GREEN`, `BASE_GREEN`, `SECONDS_PER_VEHICLE`,
  `YELLOW_TIME`, `MAX_WAIT`, `PEAK_FACTOR`, `CONGESTION_THRESHOLD` — signal
  timing engine.
- `JUNCTIONS` — id/name/lat/lng for 3–4 junctions (placeholder coordinates).
- `AMBULANCE_ROUTE`, `CORRIDOR_DISTANCE` — emergency preemption.
- `FIRESTORE_SIGNAL_WRITE_INTERVAL`, `FIRESTORE_COUNT_WRITE_INTERVAL`,
  `FIRESTORE_VIOLATION_WRITE_INTERVAL` — write cadence.
- `AIR_QUALITY_REFRESH_INTERVAL` — AQI polling cadence.

## 6. Architecture / Data Flow

```
lane videos ──▶ detection (YOLOv8) ──▶ per-lane vehicle counts
                                           │
                                           ▼
                          signal_control (adaptive timing engine)
                                           │        ▲
                             congestion ───┘        │ override
                            classifier (ml)         │
                                           │   ambulance (corridor preemption)
                                           ▼
                                   firebase (Firestore)
                                           │
                     ┌─────────────────────┼─────────────────────┐
                     ▼                     ▼                     ▼
              violations (images)   airquality (AQI)      Flutter dashboard
```

`main.py` (Phase 10) is the only piece that imports and wires every module
together; each module stays independently testable before that point.

## 7. Build Phases

1. **Project Setup** — folder structure, venv, `requirements.txt`,
   `config.py`, `.env.example`, `.gitignore`, `README.md`.
2. **Vehicle Detection** — YOLOv8n per-lane video processing, ROI
   filtering, per-frame/per-lane vehicle counts, debug overlay window.
2a. **Custom Model Fine-Tuning (local GPU, optional upgrade to Phase 2)** —
    fine-tune `yolov8n.pt` on the `UVH-26` dataset (14 fine-grained Indian
    vehicle classes, merged down to this project's existing 4 —
    car/bike/bus/truck — see `backend/training/finetune_uvh26.py` for the
    exact mapping) using the dev laptop's own RTX 4050 GPU, from a
    separate CUDA-enabled venv (never the project's main CPU-only venv);
    copy the resulting `best.pt` into `backend/data/models/`, point
    `config.MODEL_PATH` at it, and update `detector.py`'s `CLASS_NAMES` +
    `config.VEHICLE_CLASS_IDS` from COCO ids (2/3/5/7) to the new model's
    own class ids (0/1/2/3, order defined in `data.yaml`). Only needed if
    stock COCO weights under-detect vehicle classes (e.g. motorcycles) on
    your actual lane footage — see section 8a for the workflow and
    section 5 for the `CLASS_CONFIDENCE_OVERRIDES` stopgap this can
    replace. If training ever needs to happen on a machine without a GPU,
    `backend/training/uvh26_finetune.ipynb` runs the same steps in Colab.
3. **Stop-Line Violation Detection** — detect a vehicle crossing a lane's
   stop line while that lane is red; save a snapshot + timestamp + lane id.
4. **Adaptive Signal Timing Engine** — 4-phase state machine computing each
   lane's green duration from live vehicle counts using the constants in
   `config.py`.
5. **Congestion Classification Model** — build a small labeled
   counts/time-of-day dataset, train a scikit-learn classifier
   (low/medium/high), persist with `joblib`, feed it into the timing engine
   as a peak-factor trigger.
6. **Firebase Integration** — Firestore client; push signal states, vehicle
   counts, and violations on the configured intervals.
7. **Ambulance Priority Corridor** — simulate GPS progress along
   `AMBULANCE_ROUTE`; when within `CORRIDOR_DISTANCE` of a junction, force
   that junction's lane to green and restore normal cycling after it passes.
8. **Air Quality Monitoring** — poll the OpenWeatherMap Air Pollution API
   per junction on `AIR_QUALITY_REFRESH_INTERVAL`; push AQI to Firestore.
9. **Flutter Dashboard App** — `flutter create`; live junction map, signal
   status, vehicle counts, violation gallery, ambulance tracker, AQI widget,
   all bound to Firestore.
10. **Integration, Testing & Demo Prep** — `main.py` orchestrator wiring
    Phases 2–8 together, end-to-end dry run, CPU performance tuning, a
    demo script/checklist and a pre-recorded fallback in case live
    detection misbehaves on stage.

## 8. Hardware & Performance Notes (8 GB RAM, i5, Windows, RTX 4050 6 GB GPU)

- **Torch install size**: `ultralytics` pulls in PyTorch. The default PyPI
  wheel bundles CUDA support you don't need and is 2–3 GB. Install the
  CPU-only wheel first (`--index-url https://download.pytorch.org/whl/cpu`)
  before installing `requirements.txt`, see Phase 1 commands below.
- **4 lanes is not free real-time**: running YOLOv8 on four video streams
  truly concurrently will strain a CPU-only i5. Process lanes sequentially
  per cycle, downscale frames (e.g. 640×360), and/or skip frames
  (process every 2nd–3rd frame) rather than aiming for 4-way live concurrency.
- **RAM pressure during the demo**: VS Code + the Python venv + OpenCV
  windows + Android Studio/emulator together can exceed 8 GB. Prefer
  `flutter run -d chrome` or a physical phone over an Android emulator.
- **Firestore free-tier quota**: Spark plan allows ~20K writes/day. The
  default write intervals (2s/5s across 4 junctions) are fine for short
  demo sessions but would burn through quota over a full day left running —
  treat those intervals as "demo mode," not "run forever" settings.
- **OpenWeatherMap free tier**: 60 calls/min, 1,000/day. The default
  10-minute AQI refresh across 4 junctions stays comfortably inside that;
  don't lower it much further without checking the quota.
- **Inference stays CPU-only by design, training uses the GPU
  opportunistically**: Phase 2 (and everything else — the main app,
  `main.py`, the demo) runs against the CPU-only PyTorch wheel in
  `backend/requirements.txt`, so the project still works on a GPU-less
  machine. Phase 2a is the one exception: it trains on this specific
  laptop's RTX 4050 from a **separate** CUDA-enabled venv, never the main
  one — don't let a CUDA-enabled torch install leak into the main venv,
  that would change Phase 1's "no GPU needed" guarantee for anyone else
  running this project.

### 8a. Custom YOLO Fine-Tuning Workflow (Phase 2a, local GPU)

- **Where training happens**: a dedicated venv at `backend/training/venv_train`
  with a CUDA-enabled PyTorch build, kept entirely separate from the
  project's main CPU-only venv. Set it up once:
  ```
  python -m venv backend/training/venv_train
  backend\training\venv_train\Scripts\activate
  pip install torch --index-url https://download.pytorch.org/whl/cu124
  pip install -r backend/training/requirements-train.txt
  ```
  (cu124 matches the driver's reported CUDA 12.4; check
  `nvidia-smi`/the PyTorch install selector if the driver changes later.)
- **Dataset**: `UVH-26` on Hugging Face (Bucket `Vikas-mandlik/UVH-26-bucket`,
  ~84 GB on disk — `UVH-26-Train` 21,349 images, `UVH-26-Val` 5,299
  images). 14 raw classes (Hatchback/Sedan/SUV/MUV/Bus/Truck/
  Three-wheeler/Two-wheeler/LCV/Mini-bus/Tempo-traveller/Bicycle/Van/
  Others), merged down to this project's 4 (car/bike/bus/truck) — see the
  mapping in `backend/training/finetune_uvh26.py`. Annotations are
  **plain COCO format** (`UVH-26-MV-Train.json`/`-Val.json`: top-level
  `images`/`annotations`/`categories` lists, `bbox` as
  `[x, y, width, height]` absolute pixels, category ids 1-14) — confirmed
  against the actual downloaded JSON, not just the dataset card, which
  describes the `datasets`-library feature schema rather than the raw
  file layout. The script still does a visual sanity-check step (saves an
  annotated sample image) before converting the full dataset. Buckets
  download via the `hf` CLI's
  `hf sync hf://buckets/Vikas-mandlik/UVH-26-bucket <dest>`, not the
  regular `snapshot_download()` dataset API — confirmed via the bucket's
  own "Sync this bucket" dialog, and `hf sync` can stall silently (zero
  byte growth, stuck process, no error) — if progress flatlines for 10+
  minutes while the process still shows CPU activity, kill it and
  re-run; it resumes without re-downloading completed files. ~84 GB also
  means checking free disk space before downloading, separate from the
  RAM constraint above.
- **Base weights**: start from `yolov8n.pt` (same architecture already in
  `config.py`) so inference speed stays the same — do not move up to
  `yolov8s`/`m` for this project.
- **Running it**: from the `venv_train` environment,
  `python backend/training/finetune_uvh26.py <step>` where `<step>` is
  `login` → `download` → `inspect` → `convert` → `train`, in that order.
  Don't skip `inspect` — it's the only point where you confirm the bbox
  convention (by opening the saved `uvh26_sample_check.png`) before the
  full dataset gets converted.
- **After training**: copy `best.pt` from
  `backend/training/uvh26_runs/yolov8n_uvh26/weights/best.pt` into
  `backend/data/models/` (e.g. `yolov8n_uvh26.pt`), then point
  `config.MODEL_PATH` / `YOLO_MODEL_NAME` at it from the **main** venv.
  Do not commit the downloaded dataset or training run outputs —
  gitignored like other `data/models/` contents.
- **Validate before relying on it**: re-run the Phase 2 debug overlay
  (`run_detection.py`, in the main CPU-only venv) on real lane footage
  with the new weights before deciding it's actually better than stock
  COCO + the `CLASS_CONFIDENCE_OVERRIDES` stopgap — fine-tuning is not
  guaranteed to beat threshold tuning if the dataset's camera angles/
  classes don't match your lane footage closely.
- **No local GPU on a different machine?** `backend/training/uvh26_finetune.ipynb`
  runs the identical download/inspect/convert/train steps in a free Colab
  GPU runtime instead — same dataset, same class mapping, same output.
- **Placeholder coordinates**: `JUNCTIONS` and `AMBULANCE_ROUTE` in
  `config.py` use fictional lat/lng values purely so the code runs end to
  end before you decide on a real or illustrative map area.

## 9. Testing & Demo Checklist

- [ ] `venv` activates and all Phase 1 imports succeed.
- [ ] 4 sample lane videos present in `backend/data/videos/`.
- [ ] Vehicle counts look sane on at least one lane (Phase 2).
- [ ] At least one violation capture triggers correctly in a test clip
      (Phase 3).
- [ ] Signal timing engine produces different green times for different
      vehicle counts (Phase 4).
- [ ] Firestore project created, service-account JSON downloaded, path set
      in `.env` (Phase 6).
- [ ] Ambulance simulation visibly overrides a junction's signal, then
      restores it (Phase 7).
- [ ] Flutter app reads live Firestore data without hardcoded values
      (Phase 9).
- [ ] A fallback plan exists (pre-recorded run or screen capture) in case
      live detection misbehaves during the actual demo.

## 10. Fix Prompt

Paste this whenever a step from this file breaks:

```
Something broke in Phase <N>. Here is the exact error / unexpected output:

<paste error or behavior here>

Do not jump ahead to a later phase. Diagnose the root cause against the
current project state and CLAUDE.md section 5 (config.py) and section 8
(hardware notes), fix only what's necessary to make this phase's stated
deliverables work on this machine (8 GB RAM, i5, no GPU, Windows), re-run
the verification steps for this phase, and tell me exactly what you
changed and why.
```
