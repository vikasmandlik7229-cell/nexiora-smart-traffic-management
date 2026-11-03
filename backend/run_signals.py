"""Phase 3 test harness: detection + tracking + adaptive signal controller +
fixed-time baseline + waiting/eco metrics, for the 4 lanes at junction J1.

Run from inside backend/, with the venv active:
    python run_signals.py                      # interactive, press 'q' to quit
    python run_signals.py --no-display --max-frames 300   # automated smoke test
"""
import argparse
import threading
import time

import cv2
import numpy as np

import config
from api.server import frame_buffer
from detection.detector import VehicleDetector
from detection.emergency_classifier import EmergencyClassifier, TrackVotes
from detection.lane_counter import LaneCounter
from detection.motion_tracker import MotionTracker
from detection.plate_detector import PlateDetector
from metrics import eco
from metrics.publish import MetricsPublisher
from metrics.wait_time import WaitTimeTracker
from accidents.detector import AccidentDetector
from accidents.manager import create_accident
from accidents.manager import start_background as accidents_start_background
from airquality.aqi import EcoModeManager, poll_all_junctions
from emergency.authorised import start_background as authorised_start_background
from emergency.green_corridor import GreenCorridor
from db.sql_client import get_client
from prediction.predict_short import RollingBuffer, publish as publish_short_predictions
from signals.commands import run_command_listener
from signals.controller import SignalController
from signals.display import (draw_accident_banner, draw_accident_suspect, draw_countdown,
                              draw_emergency_banner, draw_mode_banner, draw_metrics_panel, draw_traffic_light)
from signals.fixed_time_baseline import FixedTimeBaseline
from violations.red_light import RedLightDetector

LANES = ["lane1", "lane2", "lane3", "lane4"]
CELL_WIDTH = 480
CELL_HEIGHT = 360
DISPLAY_FRAME_INTERVAL = 1.0 / 20  # target display/stream refresh rate, independent of detection speed


class AllLanesReader:
    """Reads all 4 lanes' videos sequentially in ONE background thread, as
    fast as combined decode allows, independent of how slow detection is.
    This is the only way to get both smooth AND real-time playback when
    detection can't keep up with the video's native fps - two things were
    tried and rejected first:
    1. Seeking forward each iteration to "catch up" to real time - measured
       at up to 24x slower than a sequential read on the 4K lane, since
       compressed video must decode forward from the last keyframe to reach
       an arbitrary target frame.
    2. One reader thread PER lane (4 total, 5 threads overall with the main
       loop) - raw decode throughput genuinely parallelises well (~99fps
       combined measured vs ~35fps single-threaded), but with 5 threads
       all contending for the GIL, the Python-heavy main thread (NMS, box
       parsing, drawing, JPEG encoding) got measurably SLOWER than with no
       threading at all - the contention cost more than the parallelism
       gained. A single combined reader thread (2 threads total) avoids
       that, at the cost of all 4 lanes advancing in lockstep rather than
       each at its own precise pace - an acceptable trade for this project.
    """

    def __init__(self, lanes: list, video_paths: dict, frame_scale: dict):
        self.lanes = lanes
        self.frame_scale = frame_scale
        self.caps = {lane: cv2.VideoCapture(video_paths[lane]) for lane in lanes}
        for lane, cap in self.caps.items():
            if not cap.isOpened():
                raise RuntimeError(f"Could not open video for {lane}: {video_paths[lane]}")
        self._lock = threading.Lock()
        self._latest = {lane: None for lane in lanes}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            for lane in self.lanes:
                cap = self.caps[lane]
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        continue
                if self.frame_scale[lane] < 1.0:
                    s = self.frame_scale[lane]
                    frame = cv2.resize(frame, (int(frame.shape[1] * s), int(frame.shape[0] * s)))
                with self._lock:
                    self._latest[lane] = frame

    def get_latest(self, lane):
        with self._lock:
            return self._latest[lane]

    def stop(self):
        self._stop.set()


def resize_for_detection(frame):
    h, w = frame.shape[:2]
    scale = config.DETECTION_RESIZE_WIDTH / w
    return cv2.resize(frame, (config.DETECTION_RESIZE_WIDTH, int(h * scale)))


def scale_detections(detections, scale_x, scale_y):
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        det.bbox = (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
        bx, by = det.bottom_center
        det.bottom_center = (int(bx * scale_x), int(by * scale_y))
    return detections


def pcu_load(by_type: dict) -> float:
    return sum(config.PCU_WEIGHTS.get(cls, 1.0) * n for cls, n in by_type.items())


def draw_lane(frame, roi_polygon, detections, lane_count, lane_name, signal_state, red_light_detector,
              emergency_banner=None, accident_detector=None, accident_info=None):
    frame = frame.copy()
    pts = np.array(roi_polygon, dtype=np.int32)
    cv2.polylines(frame, [pts], isClosed=True, color=(255, 200, 0), thickness=2)

    red_light_detector.draw_stop_line(frame, signal_state, frame.shape[1])

    if emergency_banner and emergency_banner[0] == lane_name:
        draw_emergency_banner(frame, lane_name, emergency_banner[1])
    elif accident_info and accident_info[0] == lane_name:
        draw_accident_banner(frame, accident_info[1], accident_info[2])

    suspect_track_ids = set()
    if accident_detector:
        for susp in accident_detector.active_suspects():
            suspect_track_ids.update(susp.track_ids)

    for det in detections:
        x1, y1, x2, y2 = det.bbox
        if red_light_detector.is_flashing(det.track_id):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
            cv2.putText(frame, "VIOLATION", (x1, max(y1 - 6, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        elif det.track_id in suspect_track_ids:
            draw_accident_suspect(frame, det.bbox, "suspected accident")
        else:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{det.class_name} #{det.track_id}", (x1, max(y1 - 6, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    draw_traffic_light(frame, signal_state, top_left=(10, 10))

    banner = f"{lane_name}: {lane_count.total} vehicles, PCU {pcu_load(lane_count.by_type):.1f} [{signal_state}]"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 24), (0, 0, 0), -1)
    cv2.putText(frame, banner, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    return cv2.resize(frame, (CELL_WIDTH, CELL_HEIGHT))


def run(no_display: bool = False, max_frames: int = None, device: str = None, extra_controllers: dict = None):
    """The J1 pipeline's actual body - callable directly (e.g. from main.py)
    as well as via this module's own CLI below. `extra_controllers` (e.g.
    J2-J4's virtual-junction SignalControllers, from
    signals.virtual_junctions.start_background) lets the green corridor and
    accident manager actually act on junctions beyond J1 - without them,
    an ambulance's route could never be pre-empted past its starting
    junction, since nothing outside this process could reach those
    controllers otherwise."""
    # Downscale any lane wider than FRAME_MAX_WIDTH once, right after each
    # read, for all downstream drawing/counting/streaming work - avoids
    # decoding cost (unavoidable) turning into drawing/encoding cost too.
    # ROI/stop-line coordinates are calibrated against each video's native
    # resolution, so they're scaled by the same factor to match.
    frame_scale = {}
    for lane in LANES:
        probe = cv2.VideoCapture(config.LANE_VIDEOS[lane])
        if not probe.isOpened():
            raise RuntimeError(f"Could not open video for {lane}: {config.LANE_VIDEOS[lane]}")
        native_w = probe.get(cv2.CAP_PROP_FRAME_WIDTH) or config.FRAME_MAX_WIDTH
        frame_scale[lane] = min(1.0, config.FRAME_MAX_WIDTH / native_w)
        probe.release()

    # Each lane reads sequentially in its own background thread (see
    # LaneReader) so the video itself always plays smoothly in real time,
    # independent of how slow detection is - the main loop below only ever
    # grabs whichever frame is currently latest.
    reader = AllLanesReader(LANES, config.LANE_VIDEOS, frame_scale)

    def scale_polygon(poly, s):
        return [(int(x * s), int(y * s)) for x, y in poly]

    # One VehicleDetector (and therefore one ByteTrack tracker) per lane,
    # NOT a single shared model called in batched mode. A batched
    # model.track(list_of_frames, persist=True) call was tried for the
    # modest (~10%) throughput gain of one GPU call over four, but ByteTrack's
    # per-stream track pools in that shared multi-source mode are not fully
    # isolated in practice: under sustained real-time running, one lane's
    # stream could stop being assigned new track IDs for many seconds at a
    # stretch even though the frame kept changing and the detector was
    # clearly still seeing vehicles - since _parse_result() (correctly)
    # requires a track id to report a Detection, that showed up as a lane's
    # count silently dropping to 0 for seconds at a time. Separate detectors
    # means separate, independently-tracked streams - each lane's YOLOv8n is
    # tiny, so 4 copies cost a few tens of MB of VRAM, not a real concern.
    detectors = {lane: VehicleDetector() for lane in LANES}
    if device:
        for det in detectors.values():
            det.device = device
            det.model.to(device)
    counters = {lane: LaneCounter(scale_polygon(config.ROI_POLYGONS[lane], frame_scale[lane])) for lane in LANES}
    trackers = {lane: MotionTracker() for lane in LANES}
    # One shared PlateDetector across all 4 lanes (stateless per call, no
    # tracker involved, so sharing is safe - unlike `detectors` above).
    # Degrades gracefully: a violation is still recorded with its existing
    # full-frame + vehicle-crop evidence even if plate weights are missing.
    plate_detector = None
    try:
        plate_detector = PlateDetector()
    except Exception as exc:
        print(f"Plate detector disabled (couldn't load it) - violations will skip the plate photo: {exc}")
    red_light_detectors = {
        lane: RedLightDetector(lane, int(config.STOP_LINES[lane] * frame_scale[lane]), plate_detector=plate_detector)
        for lane in LANES
    }
    accident_detectors = {lane: AccidentDetector(lane) for lane in LANES}
    # Per-lane cooldown (not just a track-id dedup set) so demo footage that
    # loops doesn't re-report the same visual incident under fresh track IDs
    # every time it replays - see config.ACCIDENT_REPORT_COOLDOWN_S.
    last_accident_report = {lane: 0.0 for lane in LANES}

    # Emergency-vehicle classifier (detection/emergency_classifier.py) - one
    # shared instance across all 4 lanes (CLIP is heavier than the vehicle
    # detector, so unlike `detectors` above, this is deliberately NOT one
    # per lane). TrackVotes/reported sets ARE per-lane, since track IDs come
    # from each lane's own independent ByteTrack tracker and can collide
    # across lanes (lane1's track #5 and lane2's track #5 are unrelated).
    # Degrades gracefully if the weights are missing or CLIP fails to load -
    # the rest of the pipeline must keep running either way.
    emergency_classifier = None
    if config.EMERGENCY_CLS_ENABLED:
        try:
            emergency_classifier = EmergencyClassifier()
        except Exception as exc:
            print(f"Emergency-vehicle classifier disabled (couldn't load it): {exc}")
    track_votes = {lane: TrackVotes() for lane in LANES}
    reported_vision_tracks = {lane: set() for lane in LANES}
    last_emergency_cls = {"t": 0.0}

    controller = SignalController("J1", LANES)
    baseline = FixedTimeBaseline("J1", LANES)
    adaptive_wait = WaitTimeTracker("adaptive")
    fixed_wait = WaitTimeTracker("fixed")
    metrics_publisher = MetricsPublisher("J1")

    firebase_client = get_client()
    eco_manager = EcoModeManager()
    last_aqi_poll = 0.0
    all_controllers = {"J1": controller, **(extra_controllers or {})}
    green_corridor = GreenCorridor(all_controllers)
    if firebase_client.enabled:
        import threading
        threading.Thread(target=run_command_listener, args=(all_controllers,), daemon=True).start()
        authorised_start_background("J1")
        accidents_start_background(all_controllers)
    last_corridor_tick = 0.0
    emergency_banner = None  # (lane, eta_s) while an ambulance is approaching J1

    violation_test_unblock_at = None
    if config.VIOLATION_TEST_MODE:
        controller.block_lane(config.VIOLATION_TEST_LANE)
        violation_test_unblock_at = time.time() + config.VIOLATION_TEST_SECONDS
        print(f"VIOLATION_TEST_MODE: holding {config.VIOLATION_TEST_LANE} red for "
              f"{config.VIOLATION_TEST_SECONDS}s")

    last_detections = {lane: [] for lane in LANES}
    last_counts = {lane: counters[lane].count([]) for lane in LANES}

    # Detection runs in its own background thread, decoupled from the
    # display loop below. Running detection (4 sequential YOLO calls) inline
    # in the display loop used to cap the WHOLE pipeline - including simply
    # redrawing/streaming the current frame - at the detect rate (~8-9fps),
    # since detect and draw shared one loop. The reader thread was already
    # decoding far faster than that in the background, so the display only
    # ever sampled it every ~110ms, skipping several real video frames each
    # time - visible as "pause, then teleport". Splitting detection into its
    # own thread lets the display loop below redraw+stream at a much
    # higher, steadier rate, using whatever detection result is currently
    # available (at most a couple hundred ms stale) - a far smaller, more
    # acceptable tradeoff than a visibly choppy video. `state_lock` guards
    # last_detections/last_counts and accident_detectors' internal suspect
    # dict (accident_detectors[lane].active_suspects(), called from the
    # display loop's draw_lane, iterates the same dict this thread mutates
    # in accident_detectors[lane].update() - unprotected, that's a real
    # "dict changed size during iteration" risk, not just a style nit).
    # controller.tick() (the only state mutation with a real safety
    # invariant - CLAUDE.md section 9) stays exclusively in the display
    # loop; this thread only ever calls the read-only lane_state().
    state_lock = threading.Lock()
    detect_stop = threading.Event()

    def detection_loop():
        while not detect_stop.is_set():
            small_frames = {}
            small_scale = {}
            snap_frames = {}
            cycle_detections = {}
            for lane in LANES:
                frame = reader.get_latest(lane)
                if frame is None:
                    continue
                snap_frames[lane] = frame
                small = resize_for_detection(frame)
                small_frames[lane] = small
                small_scale[lane] = (frame.shape[1] / small.shape[1], frame.shape[0] / small.shape[0])

            for lane in LANES:
                if lane not in small_frames:
                    continue
                raw_detections = detectors[lane].detect(small_frames[lane])
                scale_x, scale_y = small_scale[lane]
                detections = scale_detections(raw_detections, scale_x, scale_y)
                lane_state_now = controller.lane_state(lane)
                new_violations = red_light_detectors[lane].update(detections, lane_state_now, snap_frames[lane])
                trackers[lane].update(detections)

                cycle_detections[lane] = detections

                with state_lock:
                    confirmed = accident_detectors[lane].update(detections, trackers[lane], lane_state_now)
                    last_detections[lane] = detections
                    last_counts[lane] = counters[lane].count(detections)

                # Detection/counting/tracking above is local, CPU-only, and
                # should never fail unexpectedly. Everything below touches
                # the database - a transient failure here must not take
                # down the detection thread (an unguarded Firestore call
                # did once, back when this ran on Firestore - see CLAUDE.md).
                try:
                    if firebase_client.enabled:
                        for v in new_violations:
                            firebase_client.add_violation({
                                "junctionId": controller.junction_id, "laneId": v.lane,
                                "trackId": v.track_id, "vehicleType": v.class_name,
                                "imageFile": v.image_file, "cropFile": v.crop_file,
                                "plateFile": v.plate_file,
                                "timestamp": v.timestamp,
                            })
                            firebase_client.add_alert({
                                "type": "violation", "severity": "medium", "public": False,
                                "message": f"Red-light violation on {v.lane} ({v.class_name}, track #{v.track_id}).",
                                "junctionId": controller.junction_id, "timestamp": v.timestamp, "read": False,
                            })

                        if confirmed:
                            now_acc = time.time()
                            if now_acc - last_accident_report[lane] >= config.ACCIDENT_REPORT_COOLDOWN_S:
                                arrival_rate = pcu_load(last_counts[lane].by_type) or 1
                                create_accident(controller.junction_id, None, lane, "medium", "vision",
                                                 arrival_rate_pcu_per_min=arrival_rate,
                                                 controllers={"J1": controller})
                                last_accident_report[lane] = now_acc
                except Exception as exc:
                    print(f"Database write failed for {lane} (violations/accidents), continuing: {exc}")

            # Emergency-vehicle classification: much heavier than the
            # vehicle detector (a full CLIP forward pass), so it runs on
            # its own slower cadence rather than every detection cycle, and
            # as one batched call across every lane's car/bus/truck crops
            # together - CLIP has no persistent tracker state to corrupt
            # across a batch the way ByteTrack did (see `detectors` above),
            # so batching it is safe.
            if emergency_classifier is not None:
                now_cls = time.time()
                if now_cls - last_emergency_cls["t"] >= config.EMERGENCY_CLS_INTERVAL_S:
                    last_emergency_cls["t"] = now_cls
                    crops, crop_keys = [], []
                    for lane, detections in cycle_detections.items():
                        frame = snap_frames[lane]
                        fh, fw = frame.shape[:2]
                        for det in detections:
                            if det.class_name not in ("car", "bus", "truck"):
                                continue
                            x1, y1, x2, y2 = det.bbox
                            x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, fw), min(y2, fh)
                            if x2 <= x1 or y2 <= y1:
                                continue
                            crops.append(frame[y1:y2, x1:x2])
                            crop_keys.append((lane, det.track_id))
                    if crops:
                        try:
                            scores = emergency_classifier.score_crops(crops)
                            for (lane, tid), (score, vtype) in zip(crop_keys, scores):
                                track_votes[lane].add(tid, score, vtype)
                                status = emergency_classifier.status_for_score(track_votes[lane].track_score(tid))
                                if status and tid not in reported_vision_tracks[lane]:
                                    reported_vision_tracks[lane].add(tid)
                                    track_score = track_votes[lane].track_score(tid)
                                    best_type = track_votes[lane].track_type(tid)
                                    print(f"EMERGENCY VISION: {lane} track #{tid} looks like a "
                                          f"{best_type} (status={status}, score={track_score:.2f})")
                                    if firebase_client.enabled:
                                        # Never a real vehicleId/tagId - this can only ever become a
                                        # `vision`-sourced request (safety rule 4: recognition alone
                                        # never grants a green corridor). emergency/authorised.py
                                        # deliberately skips validating these against the RFID
                                        # registry instead of wrongly rejecting them as "unauthorised".
                                        firebase_client.add_emergency_request({
                                            "vehicleId": None, "tagId": None, "destinationJunction": None,
                                            "source": "vision", "requestedBy": "camera", "status": "pending",
                                            "reason": None, "visionConfidence": round(track_score, 3),
                                            "junctionId": controller.junction_id, "laneId": lane,
                                            "vehicleType": best_type, "timestamp": time.time(),
                                        })
                                        firebase_client.add_alert({
                                            "type": "emergency",
                                            "severity": "high" if status == "exempt" else "medium",
                                            "public": False,
                                            "message": f"Possible {best_type} spotted on {lane} by the "
                                                       f"camera (confidence {track_score:.2f}) - needs a "
                                                       f"human check before any signal priority is given.",
                                            "junctionId": controller.junction_id, "timestamp": time.time(),
                                            "read": False,
                                        })
                        except Exception as exc:
                            print(f"Emergency classifier failed this cycle, continuing without it: {exc}")

    detect_thread = threading.Thread(target=detection_loop, daemon=True)
    detect_thread.start()

    short_buffer = None
    if firebase_client.enabled:
        try:
            short_buffer = RollingBuffer()
        except FileNotFoundError:
            print("Short-term prediction skipped - no trained model yet (run prediction/train_short.py).")

    frame_idx = 0
    last_metrics_tick = time.time()
    last_signal_state = None
    last_counts_write = 0.0
    last_short_prediction_tick = 0.0

    while True:
        now_tick = time.time()
        if firebase_client.enabled and now_tick - last_corridor_tick >= 1.0:
            green_corridor.tick(firebase_client)
            last_corridor_tick = now_tick
            try:
                active_data = firebase_client.get_doc("emergency", "active") or {}
            except Exception as exc:
                print(f"emergency/active read failed, skipping this tick: {exc}")
                active_data = {}
            if active_data.get("active") and "J1" in green_corridor.held:
                emergency_banner = (green_corridor.held["J1"], active_data.get("etaNextS") or 0)
            else:
                emergency_banner = None

        loop_start = time.time()
        tiles = []
        loads = {}
        counts_now = {}
        frames = {}

        # Grab whichever frame each lane's reader thread currently has
        # latest, every single iteration - independent of how often the
        # background detection_loop (above) actually produces fresh
        # boxes/counts, so the displayed/streamed video stays smooth even
        # though the detection overlay itself only refreshes every so often.
        for lane in LANES:
            frame = reader.get_latest(lane)
            if frame is None:
                frame = np.zeros((CELL_HEIGHT, CELL_WIDTH, 3), dtype=np.uint8)  # reader hasn't produced a frame yet
            frames[lane] = frame

        for lane in LANES:
            frame = frames[lane]
            # Drawn unconditionally (not just when a local window is shown) -
            # the local API's MJPEG stream needs these annotated tiles too,
            # headless or not.
            signal_state = controller.lane_state(lane)
            with state_lock:
                detections = last_detections[lane]
                lane_count = last_counts[lane]
                loads[lane] = pcu_load(lane_count.by_type)
                counts_now[lane] = lane_count.total
                tile = draw_lane(frame, config.ROI_POLYGONS[lane], detections,
                                  lane_count, lane, signal_state, red_light_detectors[lane],
                                  emergency_banner, accident_detectors[lane])
            tiles.append(tile)
            frame_buffer.update(lane, tile)

        if violation_test_unblock_at and time.time() >= violation_test_unblock_at:
            controller.unblock_lane(config.VIOLATION_TEST_LANE)
            violation_test_unblock_at = None
            print(f"VIOLATION_TEST_MODE: released {config.VIOLATION_TEST_LANE}")

        controller.tick(loads)

        if firebase_client.enabled:
            try:
                state = controller.get_state()
                # Compare only phase/lane/mode, not the per-lane `load`
                # values - those fluctuate on every tick with real detection
                # counts, so comparing the whole dict would write on almost
                # every iteration (~4/s here) instead of "on phase change"
                # as documented, blowing well past the free-tier budget.
                comparable = (state["activeLane"], state["phase"], state["mode"])
                if comparable != last_signal_state:
                    firebase_client.write_signal("J1", state)
                    last_signal_state = comparable

                if time.time() - last_counts_write >= config.FIRESTORE_COUNT_WRITE_INTERVAL:
                    firebase_client.write_live_counts("J1", {
                        "lanes": {
                            lane: {
                                "count": last_counts[lane].total,
                                "pcu": round(loads[lane], 1),
                                "byClass": last_counts[lane].by_type,
                            }
                            for lane in LANES
                        },
                    })
                    last_counts_write = time.time()
            except Exception as exc:
                print(f"Database publish failed (signal/live_counts), continuing: {exc}")

        now = time.time()
        if now - last_metrics_tick >= 1.0:
            adaptive_states = {lane: controller.lane_state(lane) for lane in LANES}
            fixed_states = {lane: baseline.lane_state(lane) for lane in LANES}
            adaptive_wait.tick(adaptive_states, counts_now)
            fixed_wait.tick(fixed_states, counts_now)
            last_metrics_tick = now

        if firebase_client.enabled:
            try:
                metrics_publisher.maybe_publish(firebase_client, adaptive_wait, fixed_wait)
                if now - last_aqi_poll >= config.AIR_QUALITY_REFRESH_INTERVAL:
                    # Was {"J1": controller} only - eco mode could never
                    # apply to J2-J4 even when their simulated AQI was poor,
                    # since poll_all_junctions can only eco-adjust junctions
                    # whose controller it's actually given.
                    poll_all_junctions(firebase_client, eco_manager, all_controllers)
                    last_aqi_poll = now
            except Exception as exc:
                print(f"Database publish failed (metrics/AQI), continuing: {exc}")
            if short_buffer and now - last_short_prediction_tick >= 60.0:
                for lane in LANES:
                    short_buffer.push(lane, counts_now[lane])
                try:
                    predictions = short_buffer.predict_all()
                    publish_short_predictions(predictions, junction_id="J1")
                    short_buffer.check_alerts(firebase_client, "J1", predictions)
                    # Close the loop from prediction back into signal timing
                    # (CLAUDE.md 6.2: "if a lane is predicted high in 5
                    # minutes, add PREDICTION_BONUS seconds to its next
                    # green") - predicting congestion is only useful if it
                    # actually changes a signal decision.
                    for lane, pred in predictions.get("lanes", {}).items():
                        if pred.get("level") == "high":
                            controller.add_prediction_bonus(lane)
                except Exception as exc:
                    print(f"short-term prediction publish failed: {exc}")
                last_short_prediction_tick = now

        top = np.hstack(tiles[0:2])
        bottom = np.hstack(tiles[2:4])
        grid = np.vstack([top, bottom])

        draw_countdown(grid, controller.phase_ends_at, position=(grid.shape[1] - 100, 30))
        draw_mode_banner(grid, controller.get_mode(), position=(grid.shape[1] - 220, 60))
        savings = eco.savings(adaptive_wait.waiting_vehicle_seconds, fixed_wait.waiting_vehicle_seconds)
        draw_metrics_panel(grid, adaptive_wait.summary(), fixed_wait.summary(), savings,
                            top_left=(10, grid.shape[0] - 60))
        frame_buffer.update("grid", grid)

        if not no_display:
            cv2.imshow("Nexiora - Adaptive Signals (J1)", grid)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        frame_idx += 1
        if max_frames and frame_idx >= max_frames:
            break

        # Light pacing, not a detection-rate throttle: without it this loop
        # (now just a frame grab + draw + encode, no detection) would spin
        # at hundreds of fps redrawing the same reader frame over and over,
        # burning CPU for no visible benefit - ~20fps is already smoother
        # than a person tracking individual cars needs.
        elapsed = time.time() - loop_start
        if elapsed < DISPLAY_FRAME_INTERVAL:
            time.sleep(DISPLAY_FRAME_INTERVAL - elapsed)

    detect_stop.set()
    detect_thread.join(timeout=2.0)
    reader.stop()
    if not no_display:
        cv2.destroyAllWindows()

    print("\nFinal summary:")
    print(" adaptive:", adaptive_wait.summary())
    print(" fixed:   ", fixed_wait.summary())
    print(" eco:     ", eco.savings(adaptive_wait.waiting_vehicle_seconds, fixed_wait.waiting_vehicle_seconds))
    print("\nController decision log (last 10):")
    for line in controller.log[-10:]:
        print(" ", line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-display", action="store_true", help="skip cv2.imshow, for automated runs")
    parser.add_argument("--max-frames", type=int, default=None, help="stop after N frames (0 = run forever)")
    parser.add_argument("--device", default=None, help="override config.DEVICE, e.g. 'cpu' while a GPU training run is active")
    args = parser.parse_args()
    run(no_display=args.no_display, max_frames=args.max_frames, device=args.device)


if __name__ == "__main__":
    main()
