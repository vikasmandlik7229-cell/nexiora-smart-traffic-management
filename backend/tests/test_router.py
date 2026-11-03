"""Regression tests for the router/road_graph "fastest path" bug: edge
weight must reflect travel TIME (distance / speed, adjusted for congestion),
not raw distance - otherwise a shorter-but-slower road can be chosen over a
longer-but-faster one, and the reported timeS can disagree with what was
actually routed.
"""
import networkx as nx

from network.road_graph import road_time_s
from network.router import _route_time_s


def test_road_time_s_uses_speed_not_just_distance():
    slow_short = {"distanceM": 1000, "baseTimeKmph": 20, "congestionFactor": 1.0}
    fast_long = {"distanceM": 2000, "baseTimeKmph": 80, "congestionFactor": 1.0}
    # 1000m at 20km/h = 180s; 2000m at 80km/h = 90s - the longer road is
    # actually faster, so its travel time must be lower.
    assert road_time_s(fast_long) < road_time_s(slow_short)


def test_road_time_s_scales_with_congestion():
    base = {"distanceM": 1000, "baseTimeKmph": 40, "congestionFactor": 1.0}
    congested = {"distanceM": 1000, "baseTimeKmph": 40, "congestionFactor": 2.0}
    assert road_time_s(congested) == road_time_s(base) * 2


def test_shortest_simple_paths_picks_the_actually_fastest_route():
    """A direct but slow road vs. a longer but much faster detour - the
    router must pick the detour as 'fastest' since it has lower real time,
    and router.py's reported timeS must match what was optimised for."""
    graph = nx.DiGraph()
    for node in ("A", "B", "C"):
        graph.add_node(node, lat=0, lng=0)

    direct = {"distanceM": 1000, "baseTimeKmph": 10}  # 360s
    leg1 = {"distanceM": 2000, "baseTimeKmph": 80}  # 90s
    leg2 = {"distanceM": 2000, "baseTimeKmph": 80}  # 90s

    graph.add_edge("A", "B", weight=road_time_s(direct))
    graph.add_edge("A", "C", weight=road_time_s(leg1))
    graph.add_edge("C", "B", weight=road_time_s(leg2))

    paths = list(nx.shortest_simple_paths(graph, "A", "B", weight="weight"))
    fastest = paths[0]

    assert fastest == ["A", "C", "B"], "the longer-distance detour is actually faster and should win"
    assert _route_time_s(graph, fastest) == road_time_s(leg1) + road_time_s(leg2)
    assert _route_time_s(graph, fastest) < _route_time_s(graph, ["A", "B"])
