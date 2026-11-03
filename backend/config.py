"""Central configuration for the Smart Traffic Management backend.

Placeholder values (ROI polygons, stop lines, junction coordinates, ambulance
route) are fictional so the code runs end to end. Recalibrate them once real
video resolution / real-world coordinates are known (see CLAUDE.md section 8).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# Local database (replaces Firestore - see db/sql_client.py)
# ---------------------------------------------------------------------------
# A single SQLite file, free and fully local - no daily write quota, no cloud
# dependency. Every "collection" from the original Firestore design lives in
# one generic `documents` table (see db/sql_client.py's schema comment).
SQLITE_DB_PATH = BASE_DIR / os.getenv("SQLITE_DB_PATH", "data/smart_traffic.db")

# Secret used to sign login JWTs (db/auth.py). Set JWT_SECRET in .env for any
# real deployment; this fallback is fine for local-only demo/viva use.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
JWT_EXPIRY_HOURS = 12

# ---------------------------------------------------------------------------
# OpenWeather Air Pollution API (Phase 9) - empty string if not set, in which
# case airquality/aqi.py falls back to clearly-labelled simulated readings.
# ---------------------------------------------------------------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ---------------------------------------------------------------------------
# Lane video sources
# ---------------------------------------------------------------------------
VIDEOS_DIR = BASE_DIR / "videos"
LANE_VIDEOS = {
    # lane1/lane2 point at pre-downscaled copies (ffmpeg, scale=1280:-2) of the
    # original lane1.mp4 (3840x2160) / lane2.mp4 (1920x1080) - decoding a full
    # 4K/1920p frame every iteration just to immediately cv2.resize() it away
    # at runtime was expensive enough that, under the full pipeline's CPU
    # load, the single background reader thread (run_signals.py's
    # AllLanesReader) fell behind specifically on these two lanes and served
    # stale/duplicate frames for seconds at a time - visible as lane1/lane2
    # showing frozen or zero counts while lane3/lane4 (native 1080p, cheap to
    # decode) kept updating normally. Pre-downscaling once removes the
    # wasted decode cost entirely instead of threading around it further.
    # Originals are kept on disk (lane1.mp4/lane2.mp4) as backups.
    "lane1": str(VIDEOS_DIR / "lane1_1280.mp4"),
    "lane2": str(VIDEOS_DIR / "lane2_1280.mp4"),
    "lane3": str(VIDEOS_DIR / "lane3.mp4"),
    "lane4": str(VIDEOS_DIR / "lane4.mp4"),
}

# ---------------------------------------------------------------------------
# YOLO vehicle detection settings
# ---------------------------------------------------------------------------
YOLO_MODEL_NAME = "vehicle_uvh26_v8n.pt"  # fine-tuned 5-class UVH-26 model (T2/T3) - see training/reports/DETECTOR_RESULTS.md
MODEL_PATH = DATA_DIR / "models" / YOLO_MODEL_NAME
FALLBACK_MODEL_PATH = DATA_DIR / "models" / "yolov8n.pt"  # stock COCO weights, used if MODEL_PATH is missing
DEVICE = "auto"                     # "auto" = cuda if available else cpu; or force "cuda"/"cpu"
CONFIDENCE_THRESHOLD = 0.4          # default minimum detection confidence to count a box
VEHICLE_CLASS_IDS = [0, 1, 2, 3, 4]  # fine-tuned model's own ids: car, bike, auto, bus, truck (see data.yaml)
# Motorcycles are smaller and often partially occluded from an elevated street
# camera, so yolov8n sees them at lower confidence than cars/buses/trucks even
# after fine-tuning. Give class 1 (bike) a lower bar instead of lowering
# CONFIDENCE_THRESHOLD for every class. (Was class 3 under stock COCO ids;
# re-keyed to 1 for the fine-tuned model's own class ordering.)
CLASS_CONFIDENCE_OVERRIDES = {1: 0.25}
DETECTION_RESIZE_WIDTH = 640        # frames are resized to this width before running YOLO
PROCESS_EVERY_N_FRAMES = 3          # run detection every Nth frame; reuse results in between

# lane1/lane2's source videos are now pre-downscaled to this width (see
# LANE_VIDEOS above), so their native width already equals this and
# run_signals.py's per-frame cv2.resize() is a no-op for every lane. Frames
# above this width (none currently) still get downscaled once, immediately
# after cap.read(), for all drawing/counting/streaming work.
FRAME_MAX_WIDTH = 1280

# ---------------------------------------------------------------------------
# Region of interest (ROI) polygon per lane, in pixel coordinates (x, y)
# lane1/lane2 were originally calibrated against the native 3840x2160 /
# 1920x1080 videos and scaled by 1/3 and 2/3 respectively at runtime; now
# that the source videos themselves are pre-downscaled to 1280px wide (see
# LANE_VIDEOS), those same ratios are baked in here directly so the
# calibrated ROI shape is unchanged. lane3/lane4 are untouched (native res).
# ---------------------------------------------------------------------------
ROI_POLYGONS = {
    "lane1": [(732, 383), (389, 397), (474, 220), (615, 203), (734, 383)],
    "lane2": [(490, 358), (634, 354), (670, 506), (353, 518), (490, 362)],
    "lane3": [(227, 1291), (427, 955), (557, 960), (816, 1272), (232, 1299)],
    "lane4": [(197, 1381), (549, 907), (733, 904), (1040, 1365), (203, 1384)],
}

# ---------------------------------------------------------------------------
# Stop-line y-coordinate per lane (pixel row) - used for violation detection
# lane1/lane2 scaled the same way as ROI_POLYGONS above, for the same reason.
# ---------------------------------------------------------------------------
STOP_LINES = {
    "lane1": 392,
    "lane2": 509,
    "lane3": 1280,
    "lane4": 1395,
}

# ---------------------------------------------------------------------------
# Emergency-vehicle classifier (detection/emergency_classifier.py) - weights
# adopted from a public repo, not trained in-house (see CLAUDE.md 4.2 and
# data/models/emergency_cls/SOURCE.md). Classifies car/bus/truck crops with
# CLIP + a logistic-regression probe; never grants signal priority on its
# own (safety rule 4) - only ever raises a "vision"-sourced emergency
# request + controller alert for a human to check (VISION_EMERGENCY_POLICY).
# ---------------------------------------------------------------------------
EMERGENCY_CLS_ENABLED = True
EMERGENCY_CLS_INTERVAL_S = 1.5   # CLIP is heavier than the vehicle detector - don't run it every detection cycle
VISION_EMERGENCY_POLICY = "alert_only"  # alert the controller, who approves manually - "auto_local" (J1-only priority) is not implemented

# ---------------------------------------------------------------------------
# Red-light violation demo mode: force one lane to stay red so a violation
# is easy to trigger on stage, instead of waiting for a natural red phase
# ---------------------------------------------------------------------------
VIOLATION_TEST_MODE = False
VIOLATION_TEST_LANE = "lane1"
VIOLATION_TEST_SECONDS = 30

# ---------------------------------------------------------------------------
# Adaptive signal timing parameters (seconds unless noted)
# ---------------------------------------------------------------------------
MIN_GREEN = 10              # shortest allowed green phase, avoids starving a lane
MAX_GREEN = 60              # longest allowed green phase, avoids starving other lanes
BASE_GREEN = 15             # starting point before PCU-load adjustment
SECONDS_PER_PCU = 2.5       # extra green time added per queued PCU (passenger car unit)
YELLOW_TIME = 3             # fixed amber duration between green and red
MAX_WAIT = 90               # max seconds a lane may stay red before forced green
PEAK_FACTOR = 1.3           # multiplier applied to green time during peak hours
CONGESTION_THRESHOLD = 8    # PCU load above which a lane is considered congested
MAX_OVERRIDE_SECONDS = 60   # longest a manual controller override may force a green
PREDICTION_BONUS = 10       # extra green seconds added when a lane is predicted "high" soon
LANE_CAPACITY_PCU = 20      # PCU load treated as "lane at capacity" - buckets predictions into low/medium/high
PREDICTION_ALERT_COOLDOWN_S = 600  # "prediction" alerts fire at most once per 10 min per lane (CLAUDE.md 6.7)

# PCU (passenger car unit) weight per vehicle class - approximate, tune later
# against Indian Road Congress guidelines. "auto" only applies once the
# 5-class fine-tuned detector (CLAUDE.md 4.1) is deployed; until then the
# stock COCO detector's 4 classes (car/bike/bus/truck) are used and "auto"
# simply never appears in counts.
PCU_WEIGHTS = {"car": 1.0, "bike": 0.5, "auto": 1.0, "bus": 3.0, "truck": 3.0}

# ---------------------------------------------------------------------------
# Fixed-time baseline + waiting/eco metrics assumptions
# ---------------------------------------------------------------------------
FIXED_CYCLE_GREEN = 20          # seconds of green per lane in the fixed-time baseline
IDLE_FUEL_L_PER_HOUR = 0.6      # litres/hour burned idling - rough assumption, labelled as such in reports
CO2_KG_PER_L = 2.31             # kg CO2 per litre of petrol burned

# ---------------------------------------------------------------------------
# Junctions - placeholder ids/coordinates, replace with the real demo area
# ---------------------------------------------------------------------------
JUNCTIONS = [
    {"id": "J1", "name": "Main Street & 1st Ave", "lat": 19.0760, "lng": 72.8777},
    {"id": "J2", "name": "Main Street & 2nd Ave", "lat": 19.0800, "lng": 72.8800},
    {"id": "J3", "name": "Ring Road & Market St", "lat": 19.0840, "lng": 72.8830},
    {"id": "J4", "name": "Ring Road & College Rd", "lat": 19.0880, "lng": 72.8860},
]

# ---------------------------------------------------------------------------
# Ambulance priority corridor - ordered waypoints along the emergency route
# Placeholder values - replace once the real route through JUNCTIONS is fixed
# ---------------------------------------------------------------------------
AMBULANCE_ROUTE = [
    {"lat": 19.0750, "lng": 72.8770},  # start / hospital
    {"lat": 19.0760, "lng": 72.8777},  # passes J1
    {"lat": 19.0800, "lng": 72.8800},  # passes J2
    {"lat": 19.0840, "lng": 72.8830},  # passes J3
    {"lat": 19.0880, "lng": 72.8860},  # passes J4
]

CORRIDOR_DISTANCE = 300   # metres - radius within which a junction pre-empts to green
SAFETY_MARGIN = 10        # seconds of buffer added to queue-clearance time before pre-empting
STARTUP_LOST_TIME = 2     # seconds lost to acceleration when a stopped queue starts moving
PASS_DISTANCE = 50        # metres past a junction before the ambulance counts as "through" it
MAX_PREEMPTED_JUNCTIONS = 2  # pre-empt at most this many upcoming junctions at once

# ---------------------------------------------------------------------------
# Accident detection (heuristic, Phase 8) - rule-based, not a trained model;
# no accident dataset was found/available on this machine (CLAUDE.md 4.3),
# so this is the primary detection method, not a second opinion.
# ---------------------------------------------------------------------------
ACCIDENT_STOP_SECONDS = 20       # seconds stationary while the lane is green before suspecting an accident
COLLISION_IOU = 0.3              # bbox overlap threshold suggesting two tracks collided
ACCIDENT_CONFIRM_SECONDS = 10    # a suspected accident must persist this long before being confirmed
# Raised from 8/5 - this real recorded footage has its own real traffic
# lights/pedestrian crossings our virtual signal knows nothing about, so a
# vehicle legitimately stopped for those (not an accident) could persist
# past the old, shorter thresholds. 30s total (vs 13s before) cuts false
# positives without needing a genuine incident to be implausibly brief.
# A vehicle stopped at a REAL light in the footage normally starts moving
# again well before our virtual signal cycles back to green a second time;
# a genuinely stuck/crashed vehicle won't. Requiring the "stationary while
# green" suspicion to survive this many full green-again cycles (on top of
# ACCIDENT_CONFIRM_SECONDS) catches that distinction without any trained
# model - the collision heuristic (overlap + sudden speed drop) is a
# different, more specific pattern and isn't subject to this.
ACCIDENT_MIN_GREEN_CYCLES = 1
ACCIDENT_MAX_SIMULTANEOUS = 2    # more than this many vehicles qualifying at once = congestion, not an accident
ACCIDENT_TEST_MODE = False       # force-trigger a demo accident on startup if True
ACCIDENT_CLASSIFIER_ENABLED = False  # T5 skipped - no accident dataset available, heuristics only
ACCIDENT_REPORT_COOLDOWN_S = 300  # min time between new accident reports on the same lane (demo footage loops)

# ---------------------------------------------------------------------------
# Local API server (FastAPI, Phase 4)
# ---------------------------------------------------------------------------
API_HOST = "127.0.0.1"
API_PORT = 8000
PUBLIC_STREAM = True  # if False, /api/stream/j1 requires a controller token too
# The site runs locally only now (no Firebase Hosting deployment since the
# Phase 13 SQLite migration) - just the Vite dev server origin.
CORS_ORIGINS = ["http://localhost:5173"]

# ---------------------------------------------------------------------------
# Firebase / Firestore write cadence (seconds)
# ---------------------------------------------------------------------------
FIRESTORE_SIGNAL_WRITE_INTERVAL = 2      # how often signal state is pushed
FIRESTORE_COUNT_WRITE_INTERVAL = 5       # how often vehicle counts are pushed
FIRESTORE_VIOLATION_WRITE_INTERVAL = 0   # violations are written immediately (event-driven)
FIRESTORE_METRICS_WRITE_INTERVAL = 300   # 5 minutes - cumulative adaptive-vs-fixed metrics per junction

# ---------------------------------------------------------------------------
# Air quality refresh cadence (seconds)
# ---------------------------------------------------------------------------
AIR_QUALITY_REFRESH_INTERVAL = 600   # 10 minutes between OpenWeather AQI polls per junction
