"""Number-plate DETECTION (not OCR/reading) for violation evidence - crops
just the plate region out of an already-cropped vehicle image, so a
violation's evidence shows the plate close up alongside the full vehicle
and the full scene.

Weights are ADOPTED, not trained in-house (see
data/models/plate_detector/SOURCE.md) - same reasoning as
detection/emergency_classifier.py: no number-plate dataset of our own was
available, so this reuses a published detector instead of training one
from scratch.

Deliberately does NOT read the plate's characters (no OCR): the source
repo's OCR step needs a different Python environment (fast-plate-ocr +
onnxruntime) and multi-frame voting across a whole clip - a materially
bigger feature than "show a close-up plate photo alongside the violation",
which is all this module does.
"""
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

import config
from detection.detector import resolve_device

MODEL_PATH = Path(config.DATA_DIR) / "models" / "plate_detector" / "best.pt"
DETECT_IMGSZ = 640          # the vehicle crop is upscaled to roughly this size before searching for a plate -
                            # finds far more small/far plates than searching at native resolution (per the
                            # source repo's own measurement: ~40% more)
CONF_THRESHOLD = 0.25
MIN_PLATE_HEIGHT_PX = 12    # plates shorter than this (in the vehicle crop's own, unscaled pixels) are too
                            # small to ever be a useful photo - skip rather than save a useless smear
PAD_FRACTION = 0.1          # 10% margin kept around the detected plate box, same as the source repo


class PlateDetector:
    def __init__(self, model_path: Path = MODEL_PATH, device: Optional[str] = None):
        if not model_path.exists():
            raise FileNotFoundError(
                f"Plate detector weights not found at {model_path} - "
                f"see data/models/plate_detector/SOURCE.md.")
        self.device = device or resolve_device()
        self.model = YOLO(str(model_path))
        self.model.to(self.device)

    def detect_plate_crop(self, vehicle_crop_bgr: np.ndarray) -> Optional[np.ndarray]:
        """vehicle_crop_bgr: an already-cropped BGR image of one vehicle
        (e.g. a violation's own evidence crop). Returns a cropped BGR image
        of just the plate, or None if no plate was confidently found."""
        if vehicle_crop_bgr is None or vehicle_crop_bgr.size == 0:
            return None
        h, w = vehicle_crop_bgr.shape[:2]
        scale = DETECT_IMGSZ / max(h, w)
        searched = (cv2.resize(vehicle_crop_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                    if scale > 1 else vehicle_crop_bgr)
        sc = scale if scale > 1 else 1.0

        results = self.model.predict(searched, imgsz=DETECT_IMGSZ, conf=CONF_THRESHOLD, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None

        best_idx = int(boxes.conf.argmax())    # most confident plate only - one plate per vehicle
        x1, y1, x2, y2 = boxes.xyxy[best_idx].tolist()
        x1, y1, x2, y2 = x1 / sc, y1 / sc, x2 / sc, y2 / sc  # back to the original vehicle crop's own coordinates

        if (y2 - y1) < MIN_PLATE_HEIGHT_PX:
            return None

        mx, my = PAD_FRACTION * (x2 - x1), PAD_FRACTION * (y2 - y1)
        cx1, cy1 = int(max(0, x1 - mx)), int(max(0, y1 - my))
        cx2, cy2 = int(min(w, x2 + mx)), int(min(h, y2 + my))
        if cx2 <= cx1 or cy2 <= cy1:
            return None
        return vehicle_crop_bgr[cy1:cy2, cx1:cx2]
