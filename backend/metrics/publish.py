"""Phase 9: publishes each junction's cumulative adaptive-vs-fixed metrics
to the database `metrics/{junctionId}_{date}` every write interval,
using the WaitTimeTracker + eco.savings already computed by run_signals.py.
"""
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from metrics import eco
from metrics.wait_time import WaitTimeTracker


class MetricsPublisher:
    def __init__(self, junction_id: str, interval_s: float = None):
        interval_s = interval_s if interval_s is not None else config.FIRESTORE_METRICS_WRITE_INTERVAL
        self.junction_id = junction_id
        self.interval_s = interval_s
        self._last_publish = 0.0

    def maybe_publish(self, client, adaptive_wait: WaitTimeTracker, fixed_wait: WaitTimeTracker) -> None:
        now = time.time()
        if now - self._last_publish < self.interval_s:
            return
        self._last_publish = now

        savings = eco.savings(adaptive_wait.waiting_vehicle_seconds, fixed_wait.waiting_vehicle_seconds)
        adaptive_avg = adaptive_wait.average_wait_seconds()
        fixed_avg = fixed_wait.average_wait_seconds()
        reduction_pct = 0.0 if fixed_avg == 0 else max(0.0, (fixed_avg - adaptive_avg) / fixed_avg * 100)

        today = date.today().isoformat()
        client.write_metrics(self.junction_id, today, {
            "avgWaitAdaptiveS": adaptive_avg,
            "avgWaitFixedS": fixed_avg,
            "waitReductionPct": reduction_pct,
            "idleVehicleSecondsSaved": max(0.0, fixed_wait.waiting_vehicle_seconds - adaptive_wait.waiting_vehicle_seconds),
            "fuelSavedL": savings["fuelSavedL"],
            "co2SavedKg": savings["co2SavedKg"],
        })
