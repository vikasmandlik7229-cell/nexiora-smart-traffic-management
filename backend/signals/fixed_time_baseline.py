"""Fixed-cycle signal timing, run alongside the adaptive controller purely as
a measurement baseline - it never actually controls anything, it just lets
metrics/wait_time.py compute what waiting would have looked like without
adaptive timing.
"""
import time
from typing import List

import config

GREEN, YELLOW, RED = "green", "yellow", "red"


class FixedTimeBaseline:
    def __init__(self, junction_id: str, lanes: List[str]):
        self.junction_id = junction_id
        self.lanes = list(lanes)
        self.cycle_length = len(self.lanes) * (config.FIXED_CYCLE_GREEN + config.YELLOW_TIME)
        self.start_time = time.time()

    def _phase_at(self, now: float):
        elapsed = (now - self.start_time) % self.cycle_length
        slot = config.FIXED_CYCLE_GREEN + config.YELLOW_TIME
        index = int(elapsed // slot)
        offset = elapsed % slot
        lane = self.lanes[index]
        phase = GREEN if offset < config.FIXED_CYCLE_GREEN else YELLOW
        return lane, phase

    def lane_state(self, lane: str) -> str:
        active_lane, phase = self._phase_at(time.time())
        return phase if lane == active_lane else RED

    def get_state(self) -> dict:
        now = time.time()
        active_lane, phase = self._phase_at(now)
        return {
            "junctionId": self.junction_id,
            "activeLane": active_lane,
            "phase": phase,
            "mode": "fixed",
            "lanes": {lane: {"state": self.lane_state(lane)} for lane in self.lanes},
        }
