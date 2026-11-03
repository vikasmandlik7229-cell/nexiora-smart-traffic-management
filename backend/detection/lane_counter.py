"""Per-lane vehicle counting via ROI containment of each detection's bottom-centre point."""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import cv2
import numpy as np

from detection.detector import Detection


@dataclass
class LaneCount:
    total: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)


class LaneCounter:
    """Counts vehicles currently inside a lane's ROI polygon, deduplicated by track id."""

    def __init__(self, roi_polygon: List[Tuple[int, int]]):
        self.roi_polygon = roi_polygon
        self._polygon_np = np.array(roi_polygon, dtype=np.int32)

    def count(self, detections: List[Detection]) -> LaneCount:
        seen_track_ids = set()
        by_type: Dict[str, int] = {}

        for det in detections:
            if det.track_id in seen_track_ids:
                continue
            point = (float(det.bottom_center[0]), float(det.bottom_center[1]))
            inside = cv2.pointPolygonTest(self._polygon_np, point, False) >= 0
            if not inside:
                continue
            seen_track_ids.add(det.track_id)
            by_type[det.class_name] = by_type.get(det.class_name, 0) + 1

        return LaneCount(total=len(seen_track_ids), by_type=by_type)
