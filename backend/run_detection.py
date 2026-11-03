"""Phase 2 test harness: 4-lane YOLO detection + counting shown in a 2x2 grid.

Run from inside backend/, with the venv active:
    python run_detection.py

Press 'q' in the video window to quit.
"""
import time

import cv2
import numpy as np

import config
from detection.detector import VehicleDetector
from detection.lane_counter import LaneCounter

LANES = ["lane1", "lane2", "lane3", "lane4"]
CELL_WIDTH = 480
CELL_HEIGHT = 360


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


def draw_lane(frame, roi_polygon, detections, lane_count, lane_name):
    frame = frame.copy()
    pts = np.array(roi_polygon, dtype=np.int32)
    cv2.polylines(frame, [pts], isClosed=True, color=(255, 200, 0), thickness=2)

    for det in detections:
        x1, y1, x2, y2 = det.bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{det.class_name} #{det.track_id}"
        cv2.putText(frame, label, (x1, max(y1 - 6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    by_type = lane_count.by_type
    banner = (
        f"{lane_name}: {lane_count.total} vehicles "
        f"(cars {by_type.get('car', 0)}, bikes {by_type.get('bike', 0)}, "
        f"buses {by_type.get('bus', 0)}, trucks {by_type.get('truck', 0)})"
    )
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 24), (0, 0, 0), -1)
    cv2.putText(frame, banner, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)

    return cv2.resize(frame, (CELL_WIDTH, CELL_HEIGHT))


def main():
    caps = {lane: cv2.VideoCapture(config.LANE_VIDEOS[lane]) for lane in LANES}
    for lane, cap in caps.items():
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video for {lane}: {config.LANE_VIDEOS[lane]}")

    # Each lane needs its own detector: model.track(persist=True) keeps tracker
    # state (motion prediction, track IDs) that assumes consecutive calls come
    # from the same continuous video. Sharing one instance across 4 unrelated
    # lanes corrupts that state and silently drops most detections.
    detectors = {lane: VehicleDetector() for lane in LANES}
    counters = {lane: LaneCounter(config.ROI_POLYGONS[lane]) for lane in LANES}

    last_detections = {lane: [] for lane in LANES}
    last_counts = {lane: counters[lane].count([]) for lane in LANES}

    frame_idx = 0
    prev_time = time.time()
    fps = 0.0

    while True:
        tiles = []
        for lane in LANES:
            cap = caps[lane]
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    raise RuntimeError(f"Cannot read any frame from {lane} video")

            if frame_idx % config.PROCESS_EVERY_N_FRAMES == 0:
                small = resize_for_detection(frame)
                scale_x = frame.shape[1] / small.shape[1]
                scale_y = frame.shape[0] / small.shape[0]
                detections = scale_detections(detectors[lane].detect(small), scale_x, scale_y)
                last_detections[lane] = detections
                last_counts[lane] = counters[lane].count(detections)

            tiles.append(draw_lane(frame, config.ROI_POLYGONS[lane],
                                    last_detections[lane], last_counts[lane], lane))

        top = np.hstack(tiles[0:2])
        bottom = np.hstack(tiles[2:4])
        grid = np.vstack([top, bottom])

        now = time.time()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now
        cv2.putText(grid, f"FPS: {fps:.1f}", (grid.shape[1] - 140, grid.shape[0] - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow("Nexiora - 4 Lane Detection", grid)
        frame_idx += 1

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
