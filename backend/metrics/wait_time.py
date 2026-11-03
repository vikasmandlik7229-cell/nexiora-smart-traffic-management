"""Waiting-time model, used to compare the adaptive controller against the
fixed-time baseline.

Simplified, clearly-labelled model (not a traffic-flow simulation): every
second, every vehicle currently counted in a non-green lane adds one
"waiting vehicle-second"; every vehicle counted in a green lane counts as
one "vehicle-second served" that second. Average wait = waiting
vehicle-seconds / vehicle-seconds served. This approximates relative
waiting between adaptive and fixed timing on the same counts - it is not a
queueing simulation and shouldn't be read as exact seconds-per-car.
"""
from typing import Dict


class WaitTimeTracker:
    def __init__(self, label: str):
        self.label = label
        self.waiting_vehicle_seconds = 0.0
        self.served_vehicle_seconds = 0.0

    def tick(self, lane_states: Dict[str, str], lane_counts: Dict[str, int]) -> None:
        """Call once per second with each lane's signal state ("green"/
        "yellow"/"red") and that lane's current vehicle count."""
        for lane, state in lane_states.items():
            count = lane_counts.get(lane, 0)
            if state == "green":
                self.served_vehicle_seconds += count
            else:
                self.waiting_vehicle_seconds += count

    def average_wait_seconds(self) -> float:
        if self.served_vehicle_seconds == 0:
            return 0.0
        return self.waiting_vehicle_seconds / self.served_vehicle_seconds

    def summary(self) -> dict:
        return {
            "label": self.label,
            "waitingVehicleSeconds": self.waiting_vehicle_seconds,
            "servedVehicleSeconds": self.served_vehicle_seconds,
            "averageWaitSeconds": self.average_wait_seconds(),
        }
