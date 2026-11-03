"""Listens on `emergency_requests`: validates vehicleId + tagId + active
against `authorised_vehicles`, then either approves (creates `emergency/active`
with the fastest route) or rejects with a reason + a security alert.

Requests with source="vision" (detection/emergency_classifier.py, run from
run_signals.py's detection_loop) are deliberately SKIPPED here, not
validated: they never carry a real vehicleId/tagId by design (camera
recognition alone must never grant a green corridor - CLAUDE.md safety rule
4), so running them through validate_request() would always "reject" them
as unauthorised and raise a false security alert for what is actually a
legitimate camera sighting. Under the default VISION_EMERGENCY_POLICY =
"alert_only" (config.py), they're left as status="pending" - the
accompanying controller-only alert (raised alongside the request) is the
whole point: a human checks it, nothing here auto-approves it.
"""
import sys
import threading
import time
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.sql_client import get_client
from network.router import find_route


def validate_request(req: dict, client) -> Tuple[bool, str]:
    vehicle_id = req.get("vehicleId")
    tag_id = req.get("tagId")
    if not vehicle_id or not tag_id:
        return False, "missing vehicleId or tagId"

    data = client.get_doc("authorised_vehicles", vehicle_id)
    if data is None:
        return False, f"unknown vehicleId '{vehicle_id}'"
    if data.get("tagId") != tag_id:
        return False, "tagId does not match vehicleId"
    if not data.get("active", False):
        return False, "vehicle is not currently authorised (active=False)"
    return True, ""


def process_request(req: dict, client, start_junction: str = "J1") -> Tuple[str, str]:
    valid, reason = validate_request(req, client)
    if not valid:
        client.add_alert({
            "type": "security", "severity": "high", "public": False,
            "message": f"Rejected emergency request for vehicle '{req.get('vehicleId')}': {reason}",
            "junctionId": None, "timestamp": time.time(), "read": False,
        })
        return "rejected", reason

    destination = req.get("destinationJunction")
    route = find_route(start_junction, destination)
    if "error" in route:
        return "rejected", route["error"]

    client.write_emergency_active({
        "active": True,
        "vehicleId": req["vehicleId"],
        "lat": None, "lng": None,  # filled in by ambulance_sim as it moves
        "speedKmph": 0,
        "routeJunctions": route["fastest"]["junctions"],
        "routePolyline": route["fastest"]["polyline"],
        "nextJunctionId": route["fastest"]["junctions"][0],
        "etaNextS": None,
        "preempted": [],
        "startedAt": time.time(),
    })
    return "approved", f"route via {' -> '.join(route['fastest']['junctions'])}"


def run_authorised_listener(start_junction: str = "J1", poll_interval: float = 2.0,
                             stop_event: threading.Event = None):
    client = get_client()
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            for req in client.read_pending("emergency_requests"):
                if req.get("source") == "vision":
                    continue  # never auto-processed - see module docstring
                status, reason = process_request(req, client, start_junction)
                client._enqueue("emergency_requests", req["id"], {"status": status, "reason": reason})
                print(f"Emergency request {req['id']} (vehicle {req.get('vehicleId')}): {status} - {reason}")
        except Exception as exc:
            # A transient database hiccup must not permanently kill this
            # daemon thread - log and retry next poll instead.
            print(f"run_authorised_listener: database error, will retry: {exc}")
        time.sleep(poll_interval)


def start_background(start_junction: str = "J1", poll_interval: float = 2.0):
    stop_event = threading.Event()
    thread = threading.Thread(target=run_authorised_listener, args=(start_junction, poll_interval, stop_event), daemon=True)
    thread.start()
    return thread, stop_event


def main():
    """Run standalone (e.g. without the full run_signals.py video pipeline)
    so emergency requests from the driver app/dashboard/simulator still get
    validated against the RFID registry:
        python -m emergency.authorised
    """
    print("Listening for emergency_requests (Ctrl+C to stop)...")
    _, stop_event = start_background()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        print("\nStopped.")


if __name__ == "__main__":
    main()
