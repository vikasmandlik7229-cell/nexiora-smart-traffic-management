"""Simulates an ambulance's GPS trip: submits an emergency_request, waits
for approval, then moves smoothly along the assigned route, updating
emergency/active every second while the trip is active. Ctrl+C ends the
trip cleanly (marks emergency/active inactive) instead of leaving it stuck.

Run from backend/, with the venv active:
    python -m emergency.ambulance_sim --vehicle AMB001 --tag RFID-AMB-001 --from J1 --to J4
    python -m emergency.ambulance_sim --vehicle AMB001 --tag WRONG-TAG --from J1 --to J4  # test rejection
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from emergency.geo import eta_seconds, haversine_m
from db.sql_client import get_client


def wait_for_decision(client, request_id: str, timeout_s: float = 30.0):
    start = time.time()
    while time.time() - start < timeout_s:
        data = client.get_doc("emergency_requests", request_id)
        if data and data.get("status") in ("approved", "rejected"):
            return data
        time.sleep(1)
    return None


def interpolate(a: dict, b: dict, frac: float) -> dict:
    return {"lat": a["lat"] + (b["lat"] - a["lat"]) * frac, "lng": a["lng"] + (b["lng"] - a["lng"]) * frac}


def end_requested(client, vehicle_id: str) -> bool:
    """Checks trip_control/{vehicleId}, written by the driver portal's "End
    trip" button (the website can't write emergency/active directly)."""
    data = client.get_doc("trip_control", vehicle_id)
    return bool(data and data.get("endRequested"))


def run_trip(vehicle_id: str, tag_id: str, destination: str, speed_kmph: float, start_junction: str = "J1"):
    client = get_client()
    if not client.enabled:
        print("Database not connected - cannot run the ambulance simulation.")
        return

    request_id = client.create_doc("emergency_requests", {
        "vehicleId": vehicle_id, "tagId": tag_id, "destinationJunction": destination,
        "source": "sim", "requestedBy": "ambulance_sim", "status": "pending", "reason": "",
    })
    print(f"Submitted emergency_request {request_id} for {vehicle_id} -> {destination}. Waiting for approval...")

    decision = wait_for_decision(client, request_id)
    if decision is None:
        print("Timed out waiting for a decision - is emergency/authorised.py's listener running?")
        return
    if decision["status"] != "approved":
        print(f"Request REJECTED: {decision.get('reason')}")
        return
    print(f"Request APPROVED: {decision.get('reason')}")

    active_doc = client.get_doc("emergency", "active")
    route_junctions = active_doc["routeJunctions"]
    polyline = active_doc["routePolyline"]
    print(f"Route: {route_junctions} ({len(polyline)} waypoints)")

    start_time = time.time()
    ended_early = False
    rerouted = False
    try:
        i = 0
        while i < len(polyline) - 1:
            a, b = polyline[i], polyline[i + 1]
            segment_m = haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
            segment_s = eta_seconds(segment_m, speed_kmph)
            segment_start = time.time()

            while True:
                elapsed = time.time() - segment_start
                frac = min(1.0, elapsed / segment_s) if segment_s > 0 else 1.0
                pos = interpolate(a, b, frac)

                remaining_m = segment_m * (1 - frac)
                next_junction = route_junctions[i + 1]
                client.write_emergency_active({
                    "active": True, "vehicleId": vehicle_id,
                    "lat": pos["lat"], "lng": pos["lng"], "speedKmph": speed_kmph,
                    "routeJunctions": route_junctions, "routePolyline": polyline,
                    "nextJunctionId": next_junction, "etaNextS": eta_seconds(remaining_m, speed_kmph),
                    "startedAt": active_doc.get("startedAt"),
                    # "preempted" is deliberately NOT written here - it's
                    # owned exclusively by green_corridor.py's GreenCorridor,
                    # which runs in a separate process/thread. Writing a
                    # stale copy of it every second here would clobber
                    # GreenCorridor's real-time updates (merge=True only
                    # preserves fields this dict doesn't mention).
                })

                if end_requested(client, vehicle_id):
                    ended_early = True
                    break
                if frac >= 1.0:
                    break
                time.sleep(1.0)

            if ended_early:
                print(f"  trip ended early (driver portal) approaching {next_junction}")
                break
            print(f"  passed {route_junctions[i + 1]}")

            # Pick up a mid-trip reroute: an accident may have blocked part
            # of the remaining route, in which case accidents/manager.py
            # writes a fresh routeJunctions/routePolyline (starting from the
            # junction just reached) into emergency/active.
            latest = client.get_doc("emergency", "active") or {}
            if latest.get("rerouted") and latest.get("routeJunctions") != route_junctions:
                route_junctions = latest["routeJunctions"]
                polyline = latest["routePolyline"]
                rerouted = True
                i = 0
                print(f"  rerouted: new route {route_junctions}")
                continue
            i += 1

        travel_time_s = time.time() - start_time
        final_active = client.get_doc("emergency", "active") or {}
        estimated_saved_s = final_active.get("estimatedTimeSavedS", 0.0)
        # everPreempted (the full history) rather than preempted (only
        # what's currently held) - by trip end every junction has already
        # been passed and released, so "preempted" is always empty here.
        preempted_junctions = final_active.get("everPreempted", [])
        client.add_emergency_trip({
            "vehicleId": vehicle_id, "startedAt": start_time, "endedAt": time.time(),
            "travelTimeS": travel_time_s, "junctionsPreempted": preempted_junctions,
            "endedEarly": ended_early, "rerouted": rerouted,
            # estimatedWithoutCorridorS/timeSavedS are derived from
            # GreenCorridor's real pre-emption decisions (the queue-clearance
            # time credited each time it actually held a junction for this
            # ambulance) - a real, measured-from-this-trip estimate, not an
            # invented number, though it's still an estimate rather than a
            # measurement of an actual second, corridor-free run.
            "estimatedWithoutCorridorS": travel_time_s + estimated_saved_s,
            "timeSavedS": estimated_saved_s,
        })
        print(f"Trip {'ended early' if ended_early else 'complete'} in {travel_time_s:.1f}s.")

    except KeyboardInterrupt:
        print("\nTrip interrupted by Ctrl+C.")
    finally:
        client.write_emergency_active({"active": False, "vehicleId": None})
        client._enqueue("trip_control", vehicle_id, {"endRequested": False})
        # The database client writes through a background queue - give it a
        # moment to flush before this one-shot script's process exits.
        time.sleep(2)
        print("emergency/active cleared.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehicle", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--from", dest="start_junction", default="J1")
    parser.add_argument("--to", dest="destination", required=True)
    parser.add_argument("--speed", type=float, default=40.0, help="km/h")
    parser.add_argument("--unauthorised", action="store_true", help="deliberately submit a bad tag, to test rejection")
    args = parser.parse_args()

    tag = "INVALID-TAG-FOR-TESTING" if args.unauthorised else args.tag
    run_trip(args.vehicle, tag, args.destination, args.speed, args.start_junction)


if __name__ == "__main__":
    main()
