"""Creates an accident record, blocks the affected road/lane, computes
predicted impact, finds a detour via network/router.py (which already
excludes blocked roads - see road_graph.build_graph), alerts publicly with
the best detour, and listens for resolution to reopen everything cleanly.
"""
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from accidents.impact import predicted_impact
from db.sql_client import get_client
from emergency.geo import haversine_m
from network.router import find_route
from signals.controller import SignalController


def _notify_nearest_ambulance(client, accident_junction_id, road_id: str, accident_id: str, severity: str) -> None:
    """Finds the active authorised vehicle whose home base (baseJunction,
    db/seed.py) is closest to the accident and sends it a private
    'dispatch' alert with the accident's location - so a driver logged in
    as that vehicle sees it on their portal without anyone manually
    assigning it. Best-effort: silently does nothing if junction/vehicle
    data isn't available (e.g. a fresh database before seeding)."""
    location_junction_id = accident_junction_id or (road_id.split("_", 1)[0] if road_id and "_" in road_id else None)
    if not location_junction_id:
        return
    try:
        junctions = {j["id"]: j for j in client.list_docs("junctions", limit=1000)}
        vehicles = client.list_docs("authorised_vehicles", limit=1000)
    except Exception as exc:
        print(f"_notify_nearest_ambulance: couldn't read junctions/vehicles (non-fatal): {exc}")
        return

    accident_junction = junctions.get(location_junction_id)
    if not accident_junction:
        return

    nearest_id, nearest_dist_m = None, None
    for v in vehicles:
        if not v.get("active") or not v.get("baseJunction"):
            continue
        base = junctions.get(v["baseJunction"])
        if not base:
            continue
        dist = haversine_m(accident_junction["lat"], accident_junction["lng"], base["lat"], base["lng"])
        if nearest_dist_m is None or dist < nearest_dist_m:
            nearest_id, nearest_dist_m = v["id"], dist

    if nearest_id is None:
        return

    client.add_alert({
        "type": "dispatch", "severity": "high" if severity in ("high", "critical") else "medium",
        "public": False, "vehicleId": nearest_id, "junctionId": location_junction_id,
        "message": f"Accident near {accident_junction.get('name', location_junction_id)} "
                    f"({nearest_dist_m / 1000:.1f} km from your base) - you're the nearest available unit.",
        "timestamp": time.time(), "read": False,
    })
    print(f"Accident {accident_id}: nearest-vehicle dispatch alert sent to {nearest_id} "
          f"({nearest_dist_m / 1000:.1f} km away)")


def _reroute_active_ambulance_if_affected(client, from_j: str, to_j: str) -> None:
    """If an ambulance trip is active and its route passes through the
    road just blocked, recompute a route from its next upcoming junction to
    its original destination (find_route already excludes blocked roads)
    and write it into emergency/active, so ambulance_sim.py switches to it
    at the next junction boundary. GreenCorridor.tick() already re-reads
    routeJunctions from the database every tick rather than caching it, so
    it picks up the new route automatically - no changes needed there."""
    try:
        active = client.get_doc("emergency", "active") or {}
    except Exception as exc:
        print(f"_reroute_active_ambulance_if_affected: couldn't read emergency/active (non-fatal): {exc}")
        return

    route = active.get("routeJunctions", [])
    if not active.get("active") or (from_j not in route and to_j not in route):
        return  # no active trip, or this blocked road isn't on its route

    next_junction = active.get("nextJunctionId")
    destination = route[-1] if route else None
    if not next_junction or not destination or next_junction == destination:
        return  # nothing left to reroute (already on the final leg)

    new_route = find_route(next_junction, destination)
    if "error" in new_route:
        print(f"_reroute_active_ambulance_if_affected: no route from {next_junction} to {destination} "
              f"avoiding the blocked road {from_j}_{to_j} - ambulance continues to {next_junction} only.")
        return

    fastest = new_route["fastest"]
    client._enqueue("emergency", "active", {
        "routeJunctions": fastest["junctions"],
        "routePolyline": fastest["polyline"],
        "rerouted": True,
    })
    print(f"Active ambulance trip rerouted around blocked road {from_j}_{to_j}: new route {fastest['junctions']}")


def create_accident(junction_id: Optional[str], road_id: Optional[str], lane_id: Optional[str],
                     severity: str, method: str, arrival_rate_pcu_per_min: float,
                     controllers: Dict[str, SignalController] = None) -> str:
    client = get_client()
    accident_id = f"{road_id or junction_id or 'unknown'}_{int(time.time())}"
    impact = predicted_impact(severity, arrival_rate_pcu_per_min)

    if controllers and junction_id in (controllers or {}) and lane_id:
        controllers[junction_id].block_lane(lane_id)

    best_detour = None
    if road_id and "_" in road_id:
        from_j, to_j = road_id.split("_", 1)
        client._enqueue("roads", road_id, {"status": "blocked"})
        route = find_route(from_j, to_j)
        best_detour = route.get("fastest")

        _reroute_active_ambulance_if_affected(client, from_j, to_j)

    client.write_accident(accident_id, {
        "junctionId": junction_id, "roadId": road_id, "laneId": lane_id,
        "method": method, "severity": severity, "status": "active",
        "detectedAt": time.time(), "resolvedAt": None,
        "predictedQueue": impact["predictedQueuePcu"], "predictedDelayMin": impact["predictedDelayMin"],
        "alternativeRoutes": [best_detour] if best_detour else [],
    })

    client.add_alert({
        "type": "accident", "severity": "high" if severity in ("high", "critical") else "medium",
        "public": True,
        "message": f"Accident on {road_id or junction_id} ({severity}). "
                    f"Predicted extra delay: {impact['predictedDelayMin']:.0f} min.",
        "junctionId": junction_id, "timestamp": time.time(), "read": False,
    })
    _notify_nearest_ambulance(client, junction_id, road_id, accident_id, severity)
    print(f"Accident {accident_id} created: {severity}, predicted delay {impact['predictedDelayMin']:.1f} min")
    return accident_id


def resolve_accident(accident_id: str, road_id: Optional[str] = None, junction_id: Optional[str] = None,
                      lane_id: Optional[str] = None, controllers: Dict[str, SignalController] = None) -> None:
    client = get_client()
    client._enqueue("accidents", accident_id, {"status": "resolved", "resolvedAt": time.time()})
    if road_id:
        client._enqueue("roads", road_id, {"status": "open"})
    if controllers and junction_id in (controllers or {}) and lane_id:
        controllers[junction_id].unblock_lane(lane_id)
    client.add_alert({
        "type": "accident", "severity": "low", "public": True,
        "message": f"Road {road_id or junction_id} reopened.",
        "junctionId": junction_id, "timestamp": time.time(), "read": False,
    })
    print(f"Accident {accident_id} resolved, road/lane reopened.")


def run_resolve_listener(controllers: Dict[str, SignalController] = None, poll_interval: float = 2.0,
                          stop_event: threading.Event = None):
    """Watches for accidents whose status was externally set to 'resolving'
    (e.g. the dashboard's "Mark resolved" button) and finishes cleanup."""
    client = get_client()
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            for doc in client.read_pending("accidents", field="status", value="resolving"):
                resolve_accident(doc["id"], doc.get("roadId"), doc.get("junctionId"), doc.get("laneId"), controllers)
        except Exception as exc:
            # A transient database hiccup must not permanently kill this
            # daemon thread - log and retry next poll instead.
            print(f"run_resolve_listener: database error, will retry: {exc}")
        time.sleep(poll_interval)


def run_report_listener(controllers: Dict[str, SignalController] = None, poll_interval: float = 2.0,
                         stop_event: threading.Event = None):
    """Watches for accidents manually reported from the dashboard's "Report
    accident" button. The website can't write to `accidents` directly (see
    api/server.py's permission checks), so it writes a pending doc to
    `accident_reports` instead; this turns each one into a full accident record."""
    client = get_client()
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            for report in client.read_pending("accident_reports"):
                accident_id = create_accident(
                    report.get("junctionId"), report.get("roadId"), report.get("laneId"),
                    report.get("severity", "medium"), "manual",
                    report.get("arrivalRatePcuPerMin", 6.0), controllers,
                )
                client._enqueue("accident_reports", report["id"], {"status": "processed", "accidentId": accident_id})
        except Exception as exc:
            # A transient database hiccup must not permanently kill this
            # daemon thread - log and retry next poll instead.
            print(f"run_report_listener: database error, will retry: {exc}")
        time.sleep(poll_interval)


def start_background(controllers: Dict[str, SignalController] = None, poll_interval: float = 2.0):
    stop_event = threading.Event()
    threading.Thread(target=run_resolve_listener, args=(controllers, poll_interval, stop_event), daemon=True).start()
    threading.Thread(target=run_report_listener, args=(controllers, poll_interval, stop_event), daemon=True).start()
    return stop_event


def main():
    """Run standalone (e.g. without the full run_signals.py video pipeline)
    so manual accident reports and resolutions from the dashboard still get
    processed:
        python -m accidents.manager
    """
    print("Listening for accident_reports and resolving accidents (Ctrl+C to stop)...")
    stop_event = start_background()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        print("\nStopped.")


if __name__ == "__main__":
    main()
