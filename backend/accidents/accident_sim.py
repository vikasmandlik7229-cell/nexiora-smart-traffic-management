"""Manually trigger or resolve an accident, for demos and camera-less roads.

Run from backend/, with the venv active:
    python -m accidents.accident_sim --road J1_J2 --severity high
    python -m accidents.accident_sim --resolve <accident_id> --road J1_J2
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from accidents.manager import create_accident, resolve_accident

# The database client writes through a background queue (db/sql_client.py) -
# a one-shot CLI script that exits immediately can beat that thread to the
# punch and lose its writes. Always give it a moment to flush before exit.
_FLUSH_DELAY_S = 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--road", help="road id, e.g. J1_J2")
    parser.add_argument("--junction")
    parser.add_argument("--lane")
    parser.add_argument("--severity", default="medium", choices=["low", "medium", "high", "critical"])
    parser.add_argument("--arrival-rate", type=float, default=6.0, help="PCU/min arriving at the blocked lane")
    parser.add_argument("--resolve", metavar="ACCIDENT_ID")
    args = parser.parse_args()

    if args.resolve:
        resolve_accident(args.resolve, road_id=args.road, junction_id=args.junction, lane_id=args.lane)
        time.sleep(_FLUSH_DELAY_S)
        return

    junction_id = args.junction or (args.road.split("_")[0] if args.road else None)
    accident_id = create_accident(junction_id, args.road, args.lane, args.severity, "manual", args.arrival_rate)
    print(f"Created accident {accident_id} - resolve it later with:")
    print(f"  python -m accidents.accident_sim --resolve {accident_id} --road {args.road}")
    time.sleep(_FLUSH_DELAY_S)


if __name__ == "__main__":
    main()
