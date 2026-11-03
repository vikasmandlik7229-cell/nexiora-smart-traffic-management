"""Rule-based accident suspicion, using the existing MotionTracker - no
trained model (T5 was skipped, no accident dataset available; see
CLAUDE.md 4.3). This is the primary detection method here, not a second
opinion, and that's stated honestly rather than implied to be ML-based.

Two heuristics:
1. A track stays near-stationary for > ACCIDENT_STOP_SECONDS while its lane
   is green - if traffic is flowing, a vehicle not moving is suspicious.
2. Two tracks' boxes overlap heavily (IoU > COLLISION_IOU) and both just
   dropped speed sharply - suggests a collision.

A suspicion must persist for ACCIDENT_CONFIRM_SECONDS before being
confirmed, so a vehicle briefly stopped for a pedestrian doesn't trigger
a false alarm. For heuristic 1 specifically, confirmation also requires the
lane to have cycled back to green at least ACCIDENT_MIN_GREEN_CYCLES times
since the suspicion started: this footage has its own real traffic lights
our virtual signal knows nothing about, and a vehicle legitimately stopped
at one of those normally starts moving again well before our signal cycles
back to green a second time, whereas a genuinely stuck/crashed vehicle
won't. This doesn't apply to heuristic 2 (collision), a faster, more
specific pattern.

Both heuristics only make sense for a SMALL number of vehicles at once - an
accident blocks a lane, it doesn't normally look identical to half the
vehicles in frame simultaneously stopping. Dense/congested real footage
(a busy intersection, a red light elsewhere in the recorded video that our
virtual signal knows nothing about) can make MANY vehicles stationary or
slow down together at once; that's ordinary traffic, not several
simultaneous accidents, so new suspicions are suppressed when that many
vehicles qualify at once (see ACCIDENT_MAX_SIMULTANEOUS in config.py).
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import config


def iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class SuspectedAccident:
    reason: str
    track_ids: List[int]
    bbox: Tuple[int, int, int, int]
    first_suspected_at: float
    confirmed: bool = False
    # "stationary while green" suspicions only: how many times the lane has
    # cycled back to green since this suspicion started (see
    # ACCIDENT_MIN_GREEN_CYCLES). Not used by the collision heuristic.
    green_cycles_survived: int = 0
    _seen_non_green: bool = False  # internal: has the lane left green at least once since suspicion started


class AccidentDetector:
    def __init__(self, lane: str):
        self.lane = lane
        self._suspects: Dict[tuple, SuspectedAccident] = {}
        # "Normal" speed per track, frozen the moment it becomes part of a
        # collision suspicion (not updated every tick) - otherwise comparing
        # only to the immediately-previous tick means a sustained slowdown
        # stops looking like a "drop" after just one tick, and a real
        # collision would never survive long enough to get confirmed.
        self._baseline_speed: Dict[int, float] = {}

    def update(self, detections, motion_tracker, lane_state: str) -> List[SuspectedAccident]:
        now = time.time()
        newly_confirmed: List[SuspectedAccident] = []
        active_keys = set()

        stationary_now = [det for det in detections
                          if motion_tracker.seconds_stationary(det.track_id) > config.ACCIDENT_STOP_SECONDS]
        congested = len(stationary_now) > config.ACCIDENT_MAX_SIMULTANEOUS

        for det in detections:
            if motion_tracker.seconds_stationary(det.track_id) <= config.ACCIDENT_STOP_SECONDS:
                continue
            key = (det.track_id,)
            # Only START a new suspicion while the lane is green (a vehicle
            # stopped at red/yellow is normal, not suspicious), and not
            # amid heavy congestion (many vehicles stopped at once is a
            # traffic jam, not several simultaneous accidents). But once a
            # track IS suspected, keep tracking it regardless of the lane's
            # current colour or later congestion - it doesn't stop blocking
            # the lane just because the signal cycled, so don't let a
            # single non-green frame wipe the suspicion and force it to
            # re-confirm from scratch every cycle (this was spamming
            # duplicate accidents).
            if key not in self._suspects and (lane_state != "green" or congested):
                continue
            active_keys.add(key)
            susp = self._suspects.setdefault(key, SuspectedAccident(
                reason="stationary while green", track_ids=[det.track_id],
                bbox=det.bbox, first_suspected_at=now))
            susp.bbox = det.bbox
            if lane_state != "green":
                susp._seen_non_green = True
            elif susp._seen_non_green:
                # The lane has cycled all the way back to green again and
                # this same vehicle still hasn't moved - a real stop for a
                # light elsewhere in the footage would normally have cleared
                # by now, so this is stronger evidence of a real blockage.
                susp.green_cycles_survived += 1
                susp._seen_non_green = False
            if (not susp.confirmed
                    and susp.green_cycles_survived >= config.ACCIDENT_MIN_GREEN_CYCLES
                    and now - susp.first_suspected_at >= config.ACCIDENT_CONFIRM_SECONDS):
                susp.confirmed = True
                newly_confirmed.append(susp)

        qualifying_pairs = []
        for i, a in enumerate(detections):
            for b in detections[i + 1:]:
                if iou(a.bbox, b.bbox) < config.COLLISION_IOU:
                    continue
                speed_a, speed_b = motion_tracker.speed(a.track_id), motion_tracker.speed(b.track_id)
                base_a = self._baseline_speed.get(a.track_id, speed_a)
                base_b = self._baseline_speed.get(b.track_id, speed_b)
                dropped = (base_a > 0 and speed_a < base_a * 0.3) and (base_b > 0 and speed_b < base_b * 0.3)
                if dropped:
                    qualifying_pairs.append((a, b))
        # Same congestion guard as above - many pairs slowing down together
        # (everyone braking for the same jam) looks like several
        # simultaneous collisions under this heuristic but isn't one.
        collision_congested = len(qualifying_pairs) > config.ACCIDENT_MAX_SIMULTANEOUS

        for a, b in qualifying_pairs:
            key = tuple(sorted((a.track_id, b.track_id)))
            if key not in self._suspects and collision_congested:
                continue
            active_keys.add(key)
            merged_bbox = (min(a.bbox[0], b.bbox[0]), min(a.bbox[1], b.bbox[1]),
                           max(a.bbox[2], b.bbox[2]), max(a.bbox[3], b.bbox[3]))
            susp = self._suspects.setdefault(key, SuspectedAccident(
                reason="collision (overlap + speed drop)", track_ids=list(key),
                bbox=merged_bbox, first_suspected_at=now))
            susp.bbox = merged_bbox
            if not susp.confirmed and now - susp.first_suspected_at >= config.ACCIDENT_CONFIRM_SECONDS:
                susp.confirmed = True
                newly_confirmed.append(susp)

        for key in list(self._suspects):
            if key not in active_keys:
                del self._suspects[key]

        # Refresh the "normal" baseline only for tracks NOT currently part of
        # a collision suspicion (computed after this tick's updates), so a
        # track's baseline freezes at its pre-collision speed instead of
        # drifting down to match the collision itself.
        suspected_tracks = {tid for susp in self._suspects.values()
                             if susp.reason.startswith("collision") for tid in susp.track_ids}
        for det in detections:
            if det.track_id not in suspected_tracks:
                self._baseline_speed[det.track_id] = motion_tracker.speed(det.track_id)

        return newly_confirmed

    def active_suspects(self) -> List[SuspectedAccident]:
        return list(self._suspects.values())
