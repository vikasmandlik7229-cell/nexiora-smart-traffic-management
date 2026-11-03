"""Builds a networkx graph of junctions/roads for routing. Reads from the
database if connected (so accidents blocking a road are reflected live);
falls back to a simple chain matching db/seed.py's layout if the database
is offline, so routing still works without it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx

import config
from db.sql_client import get_client


def _fallback_roads():
    ids = [j["id"] for j in config.JUNCTIONS]
    roads = []
    for a, b in zip(ids, ids[1:]):
        for from_id, to_id in ((a, b), (b, a)):
            roads.append({"from": from_id, "to": to_id, "distanceM": 1000,
                          "baseTimeKmph": 40, "status": "open", "congestionFactor": 1.0})
    return roads


def road_time_s(road: dict) -> float:
    """Congestion-adjusted travel time for one road segment. Used as both
    the graph edge weight (so routing optimises for time) and the reported
    route timeS (router.py) - using distance alone (ignoring speed limits)
    meant the router could pick a path that wasn't actually fastest in time
    whenever roads had different speed limits, and the separately-computed
    "fastest" timeS could then disagree with what was actually routed."""
    base_speed_kmph = road.get("baseTimeKmph", 40)
    speed_mps = base_speed_kmph * 1000 / 3600
    free_flow_time_s = road["distanceM"] / speed_mps
    return free_flow_time_s * road.get("congestionFactor", 1.0)


def build_graph() -> nx.DiGraph:
    client = get_client()
    roads = []
    if client.enabled:
        roads = client.list_docs("roads", limit=1000)
    if not roads:
        roads = _fallback_roads()

    graph = nx.DiGraph()
    for j in config.JUNCTIONS:
        graph.add_node(j["id"], lat=j["lat"], lng=j["lng"])

    for road in roads:
        if road.get("status") == "blocked":
            continue  # excluded entirely, not just weighted down
        graph.add_edge(road["from"], road["to"],
                        distanceM=road["distanceM"],
                        baseTimeKmph=road.get("baseTimeKmph", 40),
                        weight=road_time_s(road))
    return graph
