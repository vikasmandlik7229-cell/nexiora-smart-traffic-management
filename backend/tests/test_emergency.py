"""Tests for the geometry helpers and authorisation logic behind the
ambulance green corridor. Firestore-dependent pieces (GreenCorridor,
authorised.process_request) are tested with a lightweight fake client
rather than a live connection, so these run offline and fast.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from emergency.geo import bearing_deg, closest_approach, eta_seconds, haversine_m


def test_haversine_known_distance():
    # Mumbai (CST) to Pune station, roughly 119 km as the crow flies.
    d = haversine_m(18.9398, 72.8355, 18.5286, 73.8744)
    assert 110_000 < d < 130_000


def test_haversine_zero_for_same_point():
    assert haversine_m(19.0, 72.0, 19.0, 72.0) == 0


def test_bearing_north():
    # point 2 directly north of point 1 -> bearing ~0
    b = bearing_deg(19.0, 72.0, 19.01, 72.0)
    assert b < 2 or b > 358


def test_bearing_east():
    b = bearing_deg(19.0, 72.0, 19.0, 72.01)
    assert abs(b - 90) < 2


def test_closest_approach_exact_match():
    approaches = {"lane1": 0, "lane2": 90, "lane3": 180, "lane4": 270}
    assert closest_approach(approaches, 0) == "lane1"
    assert closest_approach(approaches, 90) == "lane2"
    assert closest_approach(approaches, 180) == "lane3"
    assert closest_approach(approaches, 270) == "lane4"


def test_closest_approach_wraps_around_360():
    approaches = {"lane1": 0, "lane2": 90, "lane3": 180, "lane4": 270}
    assert closest_approach(approaches, 350) == "lane1"  # closer to 0/360 than to 270


def test_eta_seconds():
    # 1000m at 36 km/h (=10 m/s) should take 100s
    assert math.isclose(eta_seconds(1000, 36), 100, rel_tol=0.01)


def test_eta_seconds_zero_speed_is_infinite():
    assert eta_seconds(1000, 0) == float("inf")


# ---------------------------------------------------------------------
# Authorisation logic, using a minimal fake database client
# ---------------------------------------------------------------------
class _FakeClient:
    def __init__(self, vehicles):
        self._vehicles = vehicles
        self.alerts = []

    def get_doc(self, collection, doc_id):
        assert collection == "authorised_vehicles", f"unexpected collection: {collection}"
        return self._vehicles.get(doc_id)

    def add_alert(self, data):
        self.alerts.append(data)


VEHICLES = {
    "AMB001": {"tagId": "RFID-AMB-001", "active": True},
    "AMB_INACTIVE": {"tagId": "RFID-OLD", "active": False},
}


def test_valid_request_passes():
    from emergency.authorised import validate_request
    client = _FakeClient(VEHICLES)
    ok, reason = validate_request({"vehicleId": "AMB001", "tagId": "RFID-AMB-001"}, client)
    assert ok is True


def test_wrong_tag_rejected():
    from emergency.authorised import validate_request
    client = _FakeClient(VEHICLES)
    ok, reason = validate_request({"vehicleId": "AMB001", "tagId": "WRONG"}, client)
    assert ok is False
    assert "tagId" in reason


def test_unknown_vehicle_rejected():
    from emergency.authorised import validate_request
    client = _FakeClient(VEHICLES)
    ok, reason = validate_request({"vehicleId": "GHOST", "tagId": "anything"}, client)
    assert ok is False
    assert "unknown" in reason.lower()


def test_inactive_vehicle_rejected():
    from emergency.authorised import validate_request
    client = _FakeClient(VEHICLES)
    ok, reason = validate_request({"vehicleId": "AMB_INACTIVE", "tagId": "RFID-OLD"}, client)
    assert ok is False
    assert "not currently authorised" in reason


def test_missing_fields_rejected():
    from emergency.authorised import validate_request
    client = _FakeClient(VEHICLES)
    ok, reason = validate_request({}, client)
    assert ok is False
