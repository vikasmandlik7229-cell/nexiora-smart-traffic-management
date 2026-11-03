"""Geometry helpers for the ambulance corridor: distance, bearing, which
junction approach a vehicle is coming from, and ETA.
"""
import math
from typing import Dict

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compass bearing (0=N, 90=E, 180=S, 270=W) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lng2 - lng1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def closest_approach(junction_approaches: Dict[str, float], incoming_bearing: float) -> str:
    """Which lane's approach bearing is closest to the vehicle's direction
    of travel. junction_approaches: {"lane1": 0, "lane2": 90, ...} (compass
    degrees each lane's traffic arrives FROM)."""
    def angular_diff(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    return min(junction_approaches, key=lambda lane: angular_diff(junction_approaches[lane], incoming_bearing))


def eta_seconds(distance_m: float, speed_kmph: float) -> float:
    if speed_kmph <= 0:
        return float("inf")
    speed_mps = speed_kmph * 1000 / 3600
    return distance_m / speed_mps
