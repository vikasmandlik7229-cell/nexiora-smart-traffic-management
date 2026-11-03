"""Phase 4: simulated SignalController instances for the non-J1 junctions,
ticking every second with randomised-but-plausible loads (busier at
simulated peak hours) and publishing to the database the same way the real J1
pipeline does - just without a camera behind it.

Run standalone for a demo:
    python -m signals.virtual_junctions
"""
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from db.sql_client import get_client
from signals.controller import SignalController

LANES = ["lane1", "lane2", "lane3", "lane4"]
PEAK_HOURS = {8, 9, 18, 19}


class VirtualJunction:
    def __init__(self, junction_id: str):
        self.controller = SignalController(junction_id, LANES)
        self._last_signal_state = None
        self._last_counts_write = 0.0

    def simulated_loads(self) -> dict:
        hour = time.localtime().tm_hour
        peak_factor = 1.6 if hour in PEAK_HOURS else 1.0
        return {lane: max(0.0, random.gauss(6, 3)) * peak_factor for lane in LANES}

    def tick(self, client, now: float):
        loads = self.simulated_loads()
        self.controller.tick(loads)

        state = self.controller.get_state()
        # Compare only the fields that mean a real phase change, not the
        # whole dict - state["lanes"][*]["load"] changes every tick with
        # fresh random values, so comparing the full dict would write on
        # every tick instead of on phase change as documented, blowing the
        # Firestore free-tier write budget (same bug already fixed for J1 in
        # run_signals.py - this mirrors that fix for the virtual junctions).
        comparable = (state["activeLane"], state["phase"], state["mode"])
        if comparable != self._last_signal_state:
            client.write_signal(self.controller.junction_id, state)
            self._last_signal_state = comparable

        if now - self._last_counts_write >= config.FIRESTORE_COUNT_WRITE_INTERVAL:
            client.write_live_counts(self.controller.junction_id, {
                "lanes": {lane: {"count": round(loads[lane])} for lane in LANES},
            })
            self._last_counts_write = now


def run_virtual_junctions(junctions, stop_event: threading.Event = None):
    client = get_client()
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        now = time.time()
        for vj in junctions:
            vj.tick(client, now)
        time.sleep(1)


def start_background(junction_ids):
    """Returns (thread, stop_event, controllers) - call stop_event.set() to
    stop it. `controllers` ({junctionId: SignalController}) lets callers
    (GreenCorridor, the accident manager) actually act on these junctions'
    live signal state - without it, nothing outside this module could ever
    pre-empt or block a lane on J2-J4, since each one's SignalController
    used to live only inside this background thread with no way out."""
    junctions = [VirtualJunction(jid) for jid in junction_ids]
    controllers = {vj.controller.junction_id: vj.controller for vj in junctions}
    stop_event = threading.Event()
    thread = threading.Thread(target=run_virtual_junctions, args=(junctions, stop_event), daemon=True)
    thread.start()
    return thread, stop_event, controllers


if __name__ == "__main__":
    virtual_ids = [j["id"] for j in config.JUNCTIONS if j["id"] != "J1"]
    print(f"Running virtual junctions: {virtual_ids} (Ctrl+C to stop)")
    try:
        run_virtual_junctions(virtual_ids)
    except KeyboardInterrupt:
        print("\nStopped.")
