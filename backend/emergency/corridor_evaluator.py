"""Experiment: N simulated ambulance trips through J1->J2->J3->J4, once
WITH the green corridor active and once WITHOUT, using the real
SignalController + GreenCorridor code - just synthetic traffic loads
instead of camera input (per CLAUDE.md section 10: this is a documented
SIMULATION, not a measurement of real traffic; the WITH-vs-WITHOUT time
comparison is still fair since both runs use identical random loads and
identical controller/corridor logic).

Runs on a fake, fast-forwarded clock (not real wall time), so 20 trips at
~270s of simulated travel each finish in a couple of real seconds.

Run from backend/, with the venv active:
    python -m emergency.corridor_evaluator --trials 20
"""
import argparse
import random
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt

import config
from emergency.geo import eta_seconds, haversine_m
from emergency.green_corridor import GreenCorridor, _load_junction_lookup, approach_lane_for
from signals.controller import SignalController

ROUTE = ["J1", "J2", "J3", "J4"]
AMBULANCE_SPEED_KMPH = 40
SEGMENT_DISTANCE_M = 1000  # matches db/seed.py's seeded road segments
TICK_S = 1.0


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _random_loads(rng):
    return {f"lane{i}": max(0, rng.gauss(6, 3)) for i in range(1, 5)}


def simulate_trip(use_corridor: bool, seed: int, junction_lookup: dict) -> dict:
    """Steps simulated time forward one second at a time. The ambulance's
    remaining distance to the current junction shrinks every tick while
    travelling; pre-emption (if enabled) is evaluated every tick too, so it
    gets real lead time to turn the light green before the ambulance
    physically arrives - exactly like the live GreenCorridor does."""
    rng = random.Random(seed)
    clock = FakeClock()
    speed_mps = AMBULANCE_SPEED_KMPH * 1000 / 3600

    with patch("time.time", clock.time):
        controllers = {jid: SignalController(jid, ["lane1", "lane2", "lane3", "lane4"]) for jid in ROUTE}
        loads = {jid: _random_loads(rng) for jid in ROUTE}
        for jid, ctrl in controllers.items():
            ctrl.tick(loads[jid])

        total_wait_s = 0.0
        junctions_preempted = set()

        for seg, jid in enumerate(ROUTE[1:], start=1):
            distance_remaining = SEGMENT_DISTANCE_M
            lane = approach_lane_for(junction_lookup, jid, 0, 0) if use_corridor else "lane1"
            held = False

            # --- travelling toward this junction ---
            while distance_remaining > 0:
                for other_jid, ctrl in controllers.items():
                    ctrl.tick(loads[other_jid])

                if use_corridor:
                    eta = eta_seconds(distance_remaining, AMBULANCE_SPEED_KMPH)
                    clearance = (config.YELLOW_TIME + config.STARTUP_LOST_TIME
                                 + controllers[jid].last_loads.get(lane, 0) * config.SECONDS_PER_PCU)
                    if eta <= clearance + config.SAFETY_MARGIN:
                        controllers[jid].set_emergency(lane)
                        junctions_preempted.add(jid)
                        held = True

                clock.advance(TICK_S)
                distance_remaining -= speed_mps * TICK_S

            # --- arrived: wait here if the lane isn't green yet ---
            wait_here = 0.0
            while controllers[jid].lane_state(lane) != "green" and wait_here < config.MAX_WAIT * 2:
                for other_jid, ctrl in controllers.items():
                    ctrl.tick(loads[other_jid])
                clock.advance(TICK_S)
                wait_here += TICK_S
            total_wait_s += wait_here

            if held:
                controllers[jid].set_emergency(None)

        free_flow_s = eta_seconds(SEGMENT_DISTANCE_M, AMBULANCE_SPEED_KMPH) * (len(ROUTE) - 1)
        total_s = free_flow_s + total_wait_s
        return {"totalTimeS": total_s, "waitTimeS": total_wait_s, "junctionsPreempted": list(junctions_preempted)}


def run_experiment(trials: int):
    junction_lookup = _load_junction_lookup()
    with_corridor = [simulate_trip(True, seed=i, junction_lookup=junction_lookup) for i in range(trials)]
    without_corridor = [simulate_trip(False, seed=i, junction_lookup=junction_lookup) for i in range(trials)]

    time_saved = [w["totalTimeS"] - c["totalTimeS"] for c, w in zip(with_corridor, without_corridor)]
    avg_saved = sum(time_saved) / len(time_saved)

    print(f"Ran {trials} paired trials (same random loads, with vs without corridor).")
    print(f"Average wait WITH corridor:    {sum(t['waitTimeS'] for t in with_corridor) / trials:.1f}s")
    print(f"Average wait WITHOUT corridor: {sum(t['waitTimeS'] for t in without_corridor) / trials:.1f}s")
    print(f"Average time saved per trip:   {avg_saved:.1f}s")

    reports_dir = Path(__file__).resolve().parent.parent / "training" / "reports"
    reports_dir.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(range(trials), time_saved)
    ax.axhline(avg_saved, color="red", linestyle="--", label=f"average: {avg_saved:.1f}s")
    ax.set_xlabel("trial")
    ax.set_ylabel("time saved (s)")
    ax.set_title(f"Green corridor time saved per trip (n={trials}, simulated loads)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(reports_dir / "corridor_time_saved.png")
    print(f"Saved chart to {reports_dir / 'corridor_time_saved.png'}")

    return avg_saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()
    run_experiment(args.trials)


if __name__ == "__main__":
    main()
