"""Phase 12: single entry point that runs the whole Nexiora backend -
detection + adaptive signals for J1, simulated virtual junctions, the local
API server, and the hourly peak-hour prediction loop - in one process.

Everything that needs a human-run separate process still does (because it
stands in for independent real-world actors, not because it's optional):
    python -m emergency.ambulance_sim --vehicle AMB001 --tag RFID-AMB-001 --to J4
    python -m accidents.accident_sim --road J1_J2 --severity high
Those simulate a GPS device and a manual 911-style report, which naturally
run on their own schedule rather than inside the junction/signal loop.

Run from backend/, with the venv active:
    python main.py                              # J1 video window shown
    python main.py --no-display                 # headless (e.g. on a server)
    python main.py --no-display --max-frames 300   # automated smoke test
"""
import argparse

import config
import run_signals
from api.server import start_background as api_start_background
from prediction.predict_peak import start_background as peak_start_background
from signals.virtual_junctions import start_background as virtual_start_background


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-display", action="store_true", help="skip cv2.imshow, for automated/headless runs")
    parser.add_argument("--max-frames", type=int, default=None, help="stop J1's pipeline after N frames (testing)")
    parser.add_argument("--device", default=None, help="override config.DEVICE, e.g. 'cpu'")
    args = parser.parse_args()

    print("Starting Nexiora backend...")

    api_start_background()
    print(f"  API server:        http://{config.API_HOST}:{config.API_PORT}")

    virtual_ids = [j["id"] for j in config.JUNCTIONS if j["id"] != "J1"]
    virtual_controllers = {}
    if virtual_ids:
        _, _, virtual_controllers = virtual_start_background(virtual_ids)
        print(f"  Virtual junctions: {', '.join(virtual_ids)} (simulated counts)")

    try:
        peak_start_background(interval_s=3600)
        print("  Peak-hour prediction: running hourly")
    except FileNotFoundError:
        print("  Peak-hour prediction: SKIPPED - no trained model (run prediction/train_peak.py first)")

    print("  J1 pipeline:       starting (detection, adaptive signals, violations, accidents, "
          "emergency corridor, short-term prediction)...")
    print("  (emergency/authorised.py and accidents/manager.py's listeners start inside the J1 pipeline)\n")

    run_signals.run(no_display=args.no_display, max_frames=args.max_frames, device=args.device,
                     extra_controllers=virtual_controllers)


if __name__ == "__main__":
    main()
