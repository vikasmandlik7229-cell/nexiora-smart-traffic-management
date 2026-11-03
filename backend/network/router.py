"""Fastest route + alternatives between two junctions, with live congestion
weights (accidents excluded entirely via road_graph.build_graph()).
"""
import sys
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx

from network.road_graph import build_graph


def _route_time_s(graph: nx.DiGraph, path: list) -> float:
    # edge["weight"] IS the congestion-adjusted travel time (road_graph.py) -
    # summing it here, rather than recomputing free-flow time from
    # distance/speed, keeps the reported timeS consistent with what
    # shortest_simple_paths actually optimised for. Recomputing separately
    # (the previous approach) ignored congestionFactor entirely and could
    # disagree with which path the router considered "fastest".
    return sum(graph.edges[a, b]["weight"] for a, b in zip(path, path[1:]))


def _polyline(graph: nx.DiGraph, path: list) -> list:
    return [{"lat": graph.nodes[n]["lat"], "lng": graph.nodes[n]["lng"]} for n in path]


def find_route(start: str, end: str, max_alternatives: int = 3) -> dict:
    """Returns {"fastest": {...}, "alternatives": [...]} or {"error": ...}
    if no route exists (e.g. every road is blocked)."""
    graph = build_graph()
    if start not in graph or end not in graph:
        return {"error": f"unknown junction(s): {start}, {end}"}

    try:
        paths = list(islice(nx.shortest_simple_paths(graph, start, end, weight="weight"), max_alternatives + 1))
    except nx.NetworkXNoPath:
        return {"error": f"no route from {start} to {end} - all roads may be blocked"}

    fastest_path = paths[0]
    fastest_time = _route_time_s(graph, fastest_path)

    alternatives = []
    for path in paths[1:]:
        time_s = _route_time_s(graph, path)
        alternatives.append({
            "junctions": path,
            "polyline": _polyline(graph, path),
            "timeS": time_s,
            "extraTimeS": time_s - fastest_time,
        })

    return {
        "fastest": {
            "junctions": fastest_path,
            "polyline": _polyline(graph, fastest_path),
            "timeS": fastest_time,
        },
        "alternatives": alternatives,
    }
