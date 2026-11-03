"""Adaptive per-junction traffic signal controller.

One SignalController per junction. Exactly one approach is green or yellow
at a time; every other approach is red. Green duration scales with PCU load
(clamp(MIN_GREEN, MAX_GREEN, BASE_GREEN + SECONDS_PER_PCU * load)); a lane
waiting longer than MAX_WAIT is served next regardless of load, so no lane
starves. Modes (peak/eco/emergency/accident/manual) all route through the
same yellow-before-red transition - nothing skips yellow, including
emergency pre-emption and manual overrides.
"""
import time
from typing import Dict, List, Optional, Set

import config

GREEN, YELLOW, RED = "green", "yellow", "red"


class SignalController:
    def __init__(self, junction_id: str, lanes: List[str]):
        self.junction_id = junction_id
        self.lanes = list(lanes)

        self.base_mode = "adaptive"  # "adaptive" | "peak" | "eco"
        self.active_lane: Optional[str] = None
        self.phase: Optional[str] = None  # GREEN or YELLOW; everything else is implicitly RED
        self.phase_ends_at: float = 0.0

        self.blocked_lanes: Set[str] = set()
        self.emergency_lane: Optional[str] = None
        self.manual_override: Optional[dict] = None  # {"lane": ..., "ends_at": ..., "requested_s": ...}
        self._pending_force: Optional[str] = None

        self.wait_start: Dict[str, float] = {lane: time.time() for lane in self.lanes}
        self.prediction_bonus: Dict[str, float] = {}
        self.last_loads: Dict[str, float] = {lane: 0.0 for lane in self.lanes}
        self.log: List[str] = []

    # ------------------------------------------------------------------
    # Mode / override controls
    # ------------------------------------------------------------------
    def set_peak(self, enabled: bool) -> None:
        self.base_mode = "peak" if enabled else "adaptive"

    def set_eco(self, enabled: bool) -> None:
        self.base_mode = "eco" if enabled else "adaptive"

    def set_emergency(self, lane: Optional[str]) -> None:
        self.emergency_lane = lane
        if lane is None:
            self._maybe_release_hold()
            return
        if lane != self.active_lane:
            self._force_preempt(lane)

    def block_lane(self, lane: str) -> None:
        self.blocked_lanes.add(lane)
        if lane == self.active_lane and self.phase == GREEN:
            self._start_yellow()

    def unblock_lane(self, lane: str) -> None:
        self.blocked_lanes.discard(lane)

    def force_green(self, lane: str, seconds: float) -> None:
        seconds = min(seconds, config.MAX_OVERRIDE_SECONDS)
        now = time.time()
        self.manual_override = {"lane": lane, "ends_at": None, "requested_s": seconds}
        if lane == self.active_lane and self.phase == GREEN:
            self.phase_ends_at = now + seconds
            self.manual_override["ends_at"] = self.phase_ends_at
        else:
            self._force_preempt(lane)

    def release(self) -> None:
        self.manual_override = None
        self._maybe_release_hold()

    def add_prediction_bonus(self, lane: str, seconds: float = None) -> None:
        self.prediction_bonus[lane] = seconds if seconds is not None else config.PREDICTION_BONUS

    # ------------------------------------------------------------------
    # Internal: preemption helpers
    # ------------------------------------------------------------------
    def _force_preempt(self, lane: str) -> None:
        """Cut the current phase to yellow (never straight to a new green),
        and remember which lane must be picked once yellow ends."""
        self._pending_force = lane
        if self.phase == GREEN:
            self._start_yellow()
        # If already yellow, the pending force is honoured when it ends.

    def _maybe_release_hold(self) -> None:
        """Called when an emergency/manual hold is cleared. If it was
        currently holding the active green open, end it via yellow."""
        if self.phase == GREEN and self.active_lane is not None:
            still_held = self.emergency_lane == self.active_lane or (
                self.manual_override and self.manual_override["lane"] == self.active_lane
            )
            if not still_held:
                self._start_yellow()

    def _start_yellow(self) -> None:
        now = time.time()
        self.phase = YELLOW
        self.phase_ends_at = now + config.YELLOW_TIME

    # ------------------------------------------------------------------
    # Lane selection + green duration
    # ------------------------------------------------------------------
    def _max_wait(self) -> float:
        return config.MAX_WAIT * (0.5 if self.base_mode == "eco" else 1.0)

    def _select_next_lane(self, now: float) -> Optional[str]:
        if self._pending_force is not None:
            lane = self._pending_force
            self._pending_force = None
            if lane not in self.blocked_lanes:
                return lane
            # The forced lane (emergency pre-emption or manual override) got
            # blocked by an accident in the meantime - fall through to
            # normal selection instead of turning a blocked lane green.

        candidates = [l for l in self.lanes if l not in self.blocked_lanes]
        if not candidates:
            # Every approach is blocked (e.g. accidents on all lanes at
            # once) - there is no safe lane to turn green, so hold
            # everything red rather than green a blocked lane.
            return None

        max_wait = self._max_wait()
        starved = [l for l in candidates if now - self.wait_start.get(l, now) > max_wait]
        if starved:
            return max(starved, key=lambda l: now - self.wait_start.get(l, now))

        non_empty = [l for l in candidates if self.last_loads.get(l, 0) > 0]
        pool = non_empty if non_empty else candidates
        # Avoid immediately repeating the lane that just finished, unless it's the only option.
        if self.active_lane in pool and len(pool) > 1:
            pool = [l for l in pool if l != self.active_lane]
        return max(pool, key=lambda l: self.last_loads.get(l, 0))

    def _green_duration(self, lane: str) -> float:
        if self.manual_override and self.manual_override["lane"] == lane:
            return min(self.manual_override["requested_s"], config.MAX_OVERRIDE_SECONDS)

        pcu = self.last_loads.get(lane, 0.0)
        duration = config.BASE_GREEN + config.SECONDS_PER_PCU * pcu
        if self.base_mode == "peak":
            duration *= config.PEAK_FACTOR
        duration += self.prediction_bonus.pop(lane, 0)
        return max(config.MIN_GREEN, min(config.MAX_GREEN, duration))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def tick(self, loads: Dict[str, float]) -> None:
        now = time.time()
        self.last_loads.update(loads)

        if self.active_lane is None:
            self._advance(now)
            self._assert_single_green()
            return

        if self.phase == GREEN:
            held = self.emergency_lane == self.active_lane or (
                self.manual_override
                and self.manual_override["lane"] == self.active_lane
                and self.manual_override["ends_at"] is None
            )
            if held and now >= self.phase_ends_at:
                self.phase_ends_at = now + config.MIN_GREEN  # keep extending the hold
            elif now >= self.phase_ends_at:
                self._start_yellow()

        if self.phase == YELLOW and now >= self.phase_ends_at:
            self._advance(now)

        self._assert_single_green()

    def _advance(self, now: float) -> None:
        """Yellow (or startup) has ended - mark the old lane red and start the next green."""
        if self.active_lane is not None:
            self.wait_start[self.active_lane] = now

        next_lane = self._select_next_lane(now)
        if next_lane is None:
            # No safe lane available right now - hold everything red and
            # retry next tick (as soon as a lane is unblocked, _advance will
            # pick it up since active_lane stays None).
            self.active_lane = None
            self.phase = None
            self.phase_ends_at = now
            return

        duration = self._green_duration(next_lane)

        self.active_lane = next_lane
        self.phase = GREEN
        self.phase_ends_at = now + duration
        self.wait_start.pop(next_lane, None)
        if self.manual_override and self.manual_override["lane"] == next_lane:
            self.manual_override["ends_at"] = self.phase_ends_at

        self.log.append(
            f"[{self.junction_id}] {next_lane} -> GREEN for {duration:.1f}s "
            f"(load={self.last_loads.get(next_lane, 0):.1f}, mode={self.get_mode()})"
        )

    def _assert_single_green(self) -> None:
        active = [l for l in self.lanes if self.lane_state(l) in (GREEN, YELLOW)]
        assert len(active) <= 1, f"safety violation: multiple active lanes {active}"

    # ------------------------------------------------------------------
    # State reporting
    # ------------------------------------------------------------------
    def lane_state(self, lane: str) -> str:
        if lane == self.active_lane and self.phase in (GREEN, YELLOW):
            return self.phase
        return RED

    def get_mode(self) -> str:
        if self.manual_override is not None:
            return "manual"
        if self.emergency_lane is not None:
            return "emergency"
        if self.blocked_lanes:
            return "accident"
        return self.base_mode

    def get_state(self) -> dict:
        return {
            "junctionId": self.junction_id,
            "activeLane": self.active_lane,
            "phase": self.phase,
            "phaseEndsAt": self.phase_ends_at,
            "mode": self.get_mode(),
            "lanes": {
                lane: {
                    "state": self.lane_state(lane),
                    "load": self.last_loads.get(lane, 0.0),
                }
                for lane in self.lanes
            },
        }
