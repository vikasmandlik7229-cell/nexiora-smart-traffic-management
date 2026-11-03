"""Red-light violation detection: flags a track the moment it crosses a
lane's stop line while that lane's signal is red. Never flags on
green/yellow, never flags a track twice, and skips any track the caller
marks as an authorised emergency vehicle currently in emergency mode.
"""
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2

import config

VIOLATION_FLASH_SECONDS = 3.0      # how long the red "VIOLATION" box stays drawn
FLAG_STALE_SECONDS = 300.0         # forget a track's flagged state if unseen this long


class Violation:
    def __init__(self, lane: str, track_id: int, class_name: str, timestamp: float,
                 image_file: str, crop_file: str, plate_file: Optional[str] = None):
        self.lane = lane
        self.track_id = track_id
        self.class_name = class_name
        self.timestamp = timestamp
        self.image_file = image_file
        self.crop_file = crop_file
        self.plate_file = plate_file   # None if no plate detector was wired in, or none was confidently found


class RedLightDetector:
    def __init__(self, lane: str, stop_line_y: int, output_dir: Optional[Path] = None, plate_detector=None):
        self.lane = lane
        self.stop_line_y = stop_line_y
        self.output_dir = output_dir or (config.DATA_DIR / "violations_images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Optional (detection/plate_detector.py's PlateDetector) - None
        # means "no plate evidence", not an error, so tests and any run
        # without the extra weights keep working exactly as before.
        self.plate_detector = plate_detector

        self._last_y: Dict[int, int] = {}
        self._flagged_at: Dict[int, float] = {}
        self._flash_until: Dict[int, float] = {}
        self.violation_count = 0

    def _prune(self, now: float) -> None:
        stale = [tid for tid, t in self._flagged_at.items() if now - t > FLAG_STALE_SECONDS]
        for tid in stale:
            del self._flagged_at[tid]
            self._last_y.pop(tid, None)
            self._flash_until.pop(tid, None)

    def update(self, detections, lane_state: str, frame=None,
               is_emergency_track: Optional[Callable[[int], bool]] = None) -> List[Violation]:
        """Call once per processed frame. `frame` is the full-resolution BGR
        image for evidence capture; pass None to skip saving evidence (e.g.
        in tests)."""
        now = time.time()
        self._prune(now)
        new_violations: List[Violation] = []

        for det in detections:
            track_id = det.track_id
            _, y = det.bottom_center
            prev_y = self._last_y.get(track_id)
            self._last_y[track_id] = y

            if prev_y is None:
                continue  # first sighting of this track - nothing to compare against yet

            crossed = prev_y < self.stop_line_y <= y
            if not crossed or track_id in self._flagged_at or lane_state != "red":
                continue
            if is_emergency_track and is_emergency_track(track_id):
                continue

            self._flagged_at[track_id] = now
            self._flash_until[track_id] = now + VIOLATION_FLASH_SECONDS
            self.violation_count += 1

            image_file = crop_file = plate_file = None
            if frame is not None:
                image_file, crop_file, plate_file = self._save_evidence(frame, det, now)

            print(f"VIOLATION: {self.lane} track #{track_id} ({det.class_name}) crossed the stop line on RED")
            new_violations.append(Violation(self.lane, track_id, det.class_name, now,
                                             image_file, crop_file, plate_file))

        return new_violations

    def _save_evidence(self, frame, det, now: float):
        ts = int(now * 1000)
        image_name = f"{self.lane}_{det.track_id}_{ts}.jpg"
        crop_name = f"{self.lane}_{det.track_id}_{ts}_crop.jpg"
        plate_name = f"{self.lane}_{det.track_id}_{ts}_plate.jpg"

        x1, y1, x2, y2 = det.bbox
        annotated = frame.copy()
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(annotated, "VIOLATION", (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(self.output_dir / image_name), annotated)

        crop = frame[max(y1, 0):max(y2, 0), max(x1, 0):max(x2, 0)]
        plate_file = None
        if crop.size > 0:
            cv2.imwrite(str(self.output_dir / crop_name), crop)
            if self.plate_detector is not None:
                try:
                    plate_crop = self.plate_detector.detect_plate_crop(crop)
                    if plate_crop is not None and plate_crop.size > 0:
                        cv2.imwrite(str(self.output_dir / plate_name), plate_crop)
                        plate_file = plate_name
                except Exception as exc:
                    # Plate evidence is a bonus, not a requirement - a failure
                    # here must never stop the violation itself being recorded.
                    print(f"Plate detection failed for {self.lane} track #{det.track_id}, continuing: {exc}")

        return image_name, crop_name, plate_file

    def is_flashing(self, track_id: int) -> bool:
        until = self._flash_until.get(track_id)
        return until is not None and time.time() < until

    def draw_stop_line(self, frame, lane_state: str, frame_width: int):
        color = (0, 0, 255) if lane_state == "red" else (0, 200, 0)
        cv2.line(frame, (0, self.stop_line_y), (frame_width, self.stop_line_y), color, 2)
        cv2.putText(frame, f"Violations: {self.violation_count}", (frame_width - 220, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        return frame
