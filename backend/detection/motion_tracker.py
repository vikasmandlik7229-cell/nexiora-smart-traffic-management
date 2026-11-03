"""Per-track motion history: recent positions, speed, and time spent stationary.

Used by the signal controller (PCU load is count-based, not speed-based) and
later by accident detection (Phase 8) and red-light violations (Phase 5),
which both need "how fast is this track moving" / "how long has it been
stationary" rather than just its current box.
"""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional

HISTORY_SECONDS = 3.0                  # how much position history to keep per track
STALE_SECONDS = 5.0                    # drop a track if it hasn't been updated in this long
STATIONARY_SPEED_THRESHOLD_PX_S = 5.0  # below this speed, a track counts as "stationary"


@dataclass
class TrackHistory:
    positions: deque = field(default_factory=deque)  # (timestamp, x, y)
    last_seen: float = 0.0
    stationary_since: Optional[float] = None  # persists across pushes, unlike the position window

    def push(self, x: int, y: int, now: float) -> None:
        self.positions.append((now, x, y))
        self.last_seen = now
        cutoff = now - HISTORY_SECONDS
        while self.positions and self.positions[0][0] < cutoff:
            self.positions.popleft()

        if self.speed_px_per_s() < STATIONARY_SPEED_THRESHOLD_PX_S:
            if self.stationary_since is None:
                self.stationary_since = now
        else:
            self.stationary_since = None

    def speed_px_per_s(self) -> float:
        if len(self.positions) < 2:
            return 0.0
        t0, x0, y0 = self.positions[0]
        t1, x1, y1 = self.positions[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return dist / dt

    def seconds_stationary(self, now: float) -> float:
        if self.stationary_since is None:
            return 0.0
        return now - self.stationary_since


class MotionTracker:
    """Keeps a TrackHistory per track_id across calls to update()."""

    def __init__(self):
        self._tracks: Dict[int, TrackHistory] = {}

    def update(self, detections) -> None:
        now = time.time()
        for det in detections:
            track = self._tracks.setdefault(det.track_id, TrackHistory())
            x, y = det.bottom_center
            track.push(x, y, now)
        self._prune(now)

    def _prune(self, now: float) -> None:
        stale = [tid for tid, t in self._tracks.items() if now - t.last_seen > STALE_SECONDS]
        for tid in stale:
            del self._tracks[tid]

    def speed(self, track_id: int) -> float:
        track = self._tracks.get(track_id)
        return track.speed_px_per_s() if track else 0.0

    def seconds_stationary(self, track_id: int) -> float:
        track = self._tracks.get(track_id)
        if track is None:
            return 0.0
        return track.seconds_stationary(time.time())

    def active_track_ids(self):
        return list(self._tracks.keys())
