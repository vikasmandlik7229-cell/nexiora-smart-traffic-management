"""Watches emergency/active and pre-empts the next 1-2 junctions on the
ambulance's route: once ETA to a junction drops below its queue-clearance
time + SAFETY_MARGIN, that junction's approach lane is forced green (via
controller.set_emergency, which always transitions through yellow first -
see signals/controller.py). Once the ambulance passes a junction it's
permanently dropped from consideration, and releasing a hold lets the
controller's own no-starvation recovery logic take over naturally.
"""
import sys
import threading
import time
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from emergency.geo import bearing_deg, closest_approach, eta_seconds, haversine_m
from db.sql_client import get_client
from signals.controller import SignalController

DEFAULT_LANE = "lane1"  # used for junctions without configured approach bearings (only J1 has real ones)


def _load_junction_lookup() -> dict:
    """Junction lat/lng/approaches live in the database (seeded with real
    approach bearings for J1); config.JUNCTIONS alone has no "approaches"
    field, so fall back to it (no bearing-based lane selection) only if the
    database is offline or the read fails."""
    client = get_client()
    if client.enabled:
        try:
            docs = client.list_docs("junctions", limit=1000)
            lookup = {d["id"]: d for d in docs}
            if lookup:
                return lookup
        except Exception as exc:
            # Must not crash startup over a transient read hiccup - fall
            # back to config.JUNCTIONS below, same as the "offline" case.
            print(f"green_corridor: junction lookup read failed, using config.JUNCTIONS fallback: {exc}")
    return {j["id"]: j for j in config.JUNCTIONS}


def queue_clearance_s(controller: SignalController, lane: str) -> float:
    pcu = controller.last_loads.get(lane, 0)
    return config.YELLOW_TIME + config.STARTUP_LOST_TIME + pcu * config.SECONDS_PER_PCU


def approach_lane_for(junction_lookup: dict, junction_id: str, amb_lat: float, amb_lng: float) -> str:
    j = junction_lookup.get(junction_id)
    approaches = j.get("approaches") if j else None
    if not approaches:
        return DEFAULT_LANE
    # Bearing FROM the junction TO the ambulance = the compass direction the
    # ambulance is arriving from, which is what `approaches` is keyed by.
    bearing = bearing_deg(j["lat"], j["lng"], amb_lat, amb_lng)
    return closest_approach(approaches, bearing)


class GreenCorridor:
    def __init__(self, controllers: Dict[str, SignalController]):
        self.controllers = controllers
        self.held: Dict[str, str] = {}      # junction_id -> lane currently forced green
        self.passed: set = set()            # junction_ids the ambulance has already gone through
        # Loaded here (construction time), not at module-import time - by
        # the time main.py builds a GreenCorridor, Firebase has had a chance
        # to connect, whereas `import emergency.green_corridor` can happen
        # before that, permanently caching the no-"approaches" fallback.
        self.junction_lookup = _load_junction_lookup()
        # Running estimate of time saved by pre-emption, for emergency_trips'
        # "time saved" stat (objective 6.6/6.12's trip history panel) - a
        # real, derived-from-actual-decisions number, not invented: credited
        # once per junction, the first tick it becomes held, as the
        # queue-clearance time that junction would otherwise have cost.
        self.estimated_time_saved_s = 0.0
        # Every junction ever held this trip (a set, not self.held, which
        # only reflects what's CURRENTLY held and is always empty again by
        # the time the ambulance reaches its destination - every junction is
        # released once passed). A junction's eta can briefly flicker back
        # above the clearance+SAFETY_MARGIN threshold and then below it again
        # while approaching, dropping out of self.held and re-entering -
        # using a persistent set (checked once per junction for the whole
        # trip, not per flicker) avoids both re-crediting time-saved for the
        # same junction twice and duplicate entries in the trip-history list.
        self.ever_held: set = set()

    def _release_all(self):
        for jid in list(self.held):
            self.controllers[jid].set_emergency(None)
        self.held.clear()

    def tick(self, client) -> None:
        try:
            active = client.get_doc("emergency", "active") or {}
        except Exception as exc:
            # A transient read hiccup here must not take down the whole J1
            # pipeline - skip this tick, try again next time (called every
            # ~1s from run_signals.py).
            print(f"green_corridor.tick: database read failed, skipping this tick: {exc}")
            return

        if not active.get("active"):
            self._release_all()
            self.passed.clear()
            self.estimated_time_saved_s = 0.0
            self.ever_held = set()
            return

        route = active.get("routeJunctions", [])
        amb_lat, amb_lng = active.get("lat"), active.get("lng")
        if amb_lat is None:
            return

        for jid in route:
            if jid in self.controllers and jid not in self.passed:
                j = self.junction_lookup.get(jid)
                if j and haversine_m(amb_lat, amb_lng, j["lat"], j["lng"]) <= config.PASS_DISTANCE:
                    self.passed.add(jid)

        upcoming = [jid for jid in route if jid in self.controllers and jid not in self.passed]
        upcoming = upcoming[: config.MAX_PREEMPTED_JUNCTIONS]

        newly_held = {}
        for jid in upcoming:
            j = self.junction_lookup[jid]
            distance_m = haversine_m(amb_lat, amb_lng, j["lat"], j["lng"])
            lane = approach_lane_for(self.junction_lookup, jid, amb_lat, amb_lng)
            eta = eta_seconds(distance_m, active.get("speedKmph", 0) or 1)
            clearance = queue_clearance_s(self.controllers[jid], lane)

            if eta <= clearance + config.SAFETY_MARGIN:
                self.controllers[jid].set_emergency(lane)
                newly_held[jid] = lane
                if jid not in self.ever_held:
                    # First time ever this junction became held this trip -
                    # credit it once, even if it later flickers out of
                    # self.held and back in as eta/clearance hover near the
                    # threshold (self.ever_held, unlike self.held, never
                    # forgets a junction once it's been held).
                    self.estimated_time_saved_s += clearance
                    self.ever_held.add(jid)

        for jid in self.held:
            if jid not in newly_held:
                self.controllers[jid].set_emergency(None)
        self.held = newly_held

        client._enqueue("emergency", "active", {
            "preempted": list(self.held.keys()),
            "everPreempted": list(self.ever_held),
            "estimatedTimeSavedS": self.estimated_time_saved_s,
        })


def run_green_corridor(controllers: Dict[str, SignalController], poll_interval: float = 1.0,
                        stop_event: threading.Event = None):
    client = get_client()
    stop_event = stop_event or threading.Event()
    corridor = GreenCorridor(controllers)
    while not stop_event.is_set():
        corridor.tick(client)
        time.sleep(poll_interval)


def start_background(controllers: Dict[str, SignalController], poll_interval: float = 1.0):
    stop_event = threading.Event()
    thread = threading.Thread(target=run_green_corridor, args=(controllers, poll_interval, stop_event), daemon=True)
    thread.start()
    return thread, stop_event
