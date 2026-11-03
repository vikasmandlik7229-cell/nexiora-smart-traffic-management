"""YOLOv8 vehicle detector with persistent ByteTrack tracking."""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from pathlib import Path

import torch
from ultralytics import YOLO

import config

TRACKER_CONFIG = str(Path(__file__).resolve().parent / "bytetrack_custom.yaml")

CLASS_NAMES = {
    0: "car",
    1: "bike",
    2: "auto",
    3: "bus",
    4: "truck",
}


def resolve_device() -> str:
    if config.DEVICE == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return config.DEVICE


@dataclass
class Detection:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]    # x1, y1, x2, y2
    bottom_center: Tuple[int, int]     # used for ROI containment checks


class VehicleDetector:
    """Loads a YOLOv8 model once and tracks vehicles across frames with ByteTrack."""

    def __init__(self, model_path: Optional[str] = None, confidence: Optional[float] = None):
        resolved_path = Path(model_path) if model_path else Path(config.MODEL_PATH)
        if not resolved_path.exists() and resolved_path != Path(config.FALLBACK_MODEL_PATH):
            print(f"WARNING: model {resolved_path} not found, falling back to {config.FALLBACK_MODEL_PATH}")
            resolved_path = Path(config.FALLBACK_MODEL_PATH)
        self.device = resolve_device()
        self.model = YOLO(str(resolved_path))
        self.model.to(self.device)
        self.confidence = confidence if confidence is not None else config.CONFIDENCE_THRESHOLD
        self.class_ids = list(config.VEHICLE_CLASS_IDS)
        self.class_confidence_overrides = dict(config.CLASS_CONFIDENCE_OVERRIDES)
        # Pass the lowest threshold in play to track() itself so it doesn't
        # pre-filter detections before the per-class check below gets a look.
        self._track_conf = min([self.confidence, *self.class_confidence_overrides.values()])

    def _track_kwargs(self) -> dict:
        kwargs = dict(
            persist=True,
            conf=self._track_conf,
            classes=self.class_ids,
            tracker=TRACKER_CONFIG,
            device=self.device,
            verbose=False,
        )
        if self.device == "cuda":
            kwargs["half"] = True
        return kwargs

    def _parse_result(self, result) -> List[Detection]:
        detections: List[Detection] = []
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return detections

        for box, track_id, cls_id, conf in zip(
            boxes.xyxy.cpu().numpy(),
            boxes.id.cpu().numpy(),
            boxes.cls.cpu().numpy(),
            boxes.conf.cpu().numpy(),
        ):
            class_name = CLASS_NAMES.get(int(cls_id))
            if class_name is None:
                continue
            threshold = self.class_confidence_overrides.get(int(cls_id), self.confidence)
            if conf < threshold:
                continue
            x1, y1, x2, y2 = (int(v) for v in box)
            bottom_center = ((x1 + x2) // 2, y2)
            detections.append(
                Detection(
                    track_id=int(track_id),
                    class_name=class_name,
                    confidence=float(conf),
                    bbox=(x1, y1, x2, y2),
                    bottom_center=bottom_center,
                )
            )
        return detections

    def detect(self, frame) -> List[Detection]:
        results = self.model.track(frame, **self._track_kwargs())
        return self._parse_result(results[0])
