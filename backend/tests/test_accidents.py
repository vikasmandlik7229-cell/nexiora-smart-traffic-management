"""Tests for accident detection timing and impact calculation. Uses fake
Detection/MotionTracker objects rather than real video, same pattern as
test_red_light.py.
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from accidents.detector import AccidentDetector, iou
from accidents.impact import predicted_impact
from detection.detector import Detection


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeMotionTracker:
    """Lets a test dictate exactly what speed/stationary-time each track
    reports, instead of needing real position history."""

    def __init__(self):
        self.speeds = {}
        self.stationary = {}

    def speed(self, track_id):
        return self.speeds.get(track_id, 10.0)

    def seconds_stationary(self, track_id):
        return self.stationary.get(track_id, 0.0)


def make_det(track_id, bbox, class_name="car"):
    x1, y1, x2, y2 = bbox
    return Detection(track_id=track_id, class_name=class_name, confidence=0.9,
                      bbox=bbox, bottom_center=((x1 + x2) // 2, y2))


def test_iou_identical_boxes_is_one():
    box = (0, 0, 100, 100)
    assert iou(box, box) == 1.0


def test_iou_non_overlapping_is_zero():
    assert iou((0, 0, 10, 10), (100, 100, 110, 110)) == 0.0


def test_stationary_while_green_not_confirmed_before_threshold(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))

    tracker.stationary[1] = config.ACCIDENT_STOP_SECONDS + 1  # already "stationary long enough"
    confirmed = detector.update([det], tracker, "green")
    assert confirmed == []  # suspected, but not confirmed - needs ACCIDENT_CONFIRM_SECONDS to pass too

    clock.advance(config.ACCIDENT_CONFIRM_SECONDS - 1)
    confirmed = detector.update([det], tracker, "green")
    assert confirmed == []  # still not long enough


def test_stationary_while_green_confirmed_after_threshold(monkeypatch):
    """Confirmation requires both ACCIDENT_CONFIRM_SECONDS to have elapsed
    AND the lane to have cycled back to green at least once (
    ACCIDENT_MIN_GREEN_CYCLES) - a real light stop elsewhere in the footage
    would normally have cleared by the time our signal cycles back,
    a genuinely stuck vehicle won't."""
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))
    tracker.stationary[1] = config.ACCIDENT_STOP_SECONDS + 1

    detector.update([det], tracker, "green")
    clock.advance(1)
    detector.update([det], tracker, "red")  # light cycles away...
    clock.advance(config.ACCIDENT_CONFIRM_SECONDS)
    confirmed = detector.update([det], tracker, "green")  # ...and back to green - still stuck
    assert len(confirmed) == 1
    assert confirmed[0].reason == "stationary while green"


def test_stationary_while_green_never_confirms_within_a_single_cycle(monkeypatch):
    """The exact real-footage false-positive this guards against: a vehicle
    stopped at a real light elsewhere in the footage (not our virtual
    signal) stays stationary past ACCIDENT_STOP_SECONDS + CONFIRM_SECONDS,
    but starts moving again before our lane ever cycles back to green a
    second time. It must never be confirmed as an accident, no matter how
    much time passes within that single green phase."""
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))
    tracker.stationary[1] = config.ACCIDENT_STOP_SECONDS + 1

    detector.update([det], tracker, "green")
    for _ in range(10):
        clock.advance(config.ACCIDENT_CONFIRM_SECONDS)
        confirmed = detector.update([det], tracker, "green")  # lane never left green
        assert confirmed == []


def test_stationary_suspicion_survives_a_light_cycle(monkeypatch):
    """Regression test: a vehicle suspected while green must stay suspected
    through a red/yellow phase (it's still physically stuck there) instead
    of being wiped and forced to re-confirm from scratch every cycle - this
    was spamming duplicate accidents once per signal cycle in production."""
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))
    tracker.stationary[1] = config.ACCIDENT_STOP_SECONDS + 1

    detector.update([det], tracker, "green")  # suspected, not yet confirmed
    assert len(detector.active_suspects()) == 1

    clock.advance(1)
    detector.update([det], tracker, "red")  # light cycles - still stuck there
    assert len(detector.active_suspects()) == 1  # must NOT have been wiped

    clock.advance(config.ACCIDENT_CONFIRM_SECONDS)
    confirmed = detector.update([det], tracker, "green")
    assert len(confirmed) == 1  # confirms using the ORIGINAL first_suspected_at


def test_heavy_congestion_is_not_flagged_as_multiple_accidents(monkeypatch):
    """Regression test: many vehicles simultaneously stopped (a traffic jam,
    e.g. in dense real footage) must not each be independently flagged as a
    separate 'accident' - only a small number of simultaneously-stuck
    vehicles is suspicious."""
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    # More vehicles stuck at once than ACCIDENT_MAX_SIMULTANEOUS allows.
    n = config.ACCIDENT_MAX_SIMULTANEOUS + 3
    dets = [make_det(i, (i * 60, 10, i * 60 + 50, 50)) for i in range(n)]
    for d in dets:
        tracker.stationary[d.track_id] = config.ACCIDENT_STOP_SECONDS + 1

    detector.update(dets, tracker, "green")
    assert detector.active_suspects() == []  # congestion - none should start a suspicion

    clock.advance(config.ACCIDENT_CONFIRM_SECONDS + 1)
    confirmed = detector.update(dets, tracker, "green")
    assert confirmed == []  # still nothing confirmed


def test_small_number_stationary_still_flagged(monkeypatch):
    """A couple of genuinely stuck vehicles (below the congestion threshold)
    must still be caught - the congestion guard shouldn't blanket-suppress
    real small-scale incidents."""
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    assert config.ACCIDENT_MAX_SIMULTANEOUS >= 1
    dets = [make_det(i, (i * 60, 10, i * 60 + 50, 50)) for i in range(config.ACCIDENT_MAX_SIMULTANEOUS)]
    for d in dets:
        tracker.stationary[d.track_id] = config.ACCIDENT_STOP_SECONDS + 1

    detector.update(dets, tracker, "green")
    clock.advance(1)
    detector.update(dets, tracker, "red")
    clock.advance(config.ACCIDENT_CONFIRM_SECONDS)
    confirmed = detector.update(dets, tracker, "green")
    assert len(confirmed) == config.ACCIDENT_MAX_SIMULTANEOUS


def test_stationary_on_red_not_suspicious():
    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))
    tracker.stationary[1] = config.ACCIDENT_STOP_SECONDS + 100
    confirmed = detector.update([det], tracker, "red")  # stopped at a red light is normal
    assert confirmed == []
    assert detector.active_suspects() == []


def test_moving_vehicle_not_suspicious():
    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    det = make_det(1, (10, 10, 50, 50))
    tracker.stationary[1] = 0.0
    confirmed = detector.update([det], tracker, "green")
    assert confirmed == []


def test_collision_heuristic_confirms_after_overlap_and_speed_drop(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "time", clock.time)

    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    a = make_det(1, (10, 10, 60, 60))
    b = make_det(2, (20, 20, 70, 70))  # overlaps a significantly

    tracker.speeds[1] = tracker.speeds[2] = 15.0
    detector.update([a, b], tracker, "red")  # establish "previous" normal speed

    tracker.speeds[1] = tracker.speeds[2] = 1.0  # both suddenly nearly stopped
    detector.update([a, b], tracker, "red")
    clock.advance(config.ACCIDENT_CONFIRM_SECONDS + 1)
    confirmed = detector.update([a, b], tracker, "red")
    assert len(confirmed) == 1
    assert confirmed[0].reason.startswith("collision")


def test_collision_heuristic_ignores_one_sided_slowdown():
    detector = AccidentDetector("lane1")
    tracker = FakeMotionTracker()
    a = make_det(1, (10, 10, 60, 60))
    b = make_det(2, (20, 20, 70, 70))

    tracker.speeds[1] = tracker.speeds[2] = 15.0
    detector.update([a, b], tracker, "red")
    tracker.speeds[1] = 1.0  # only one vehicle slows - e.g. just braking, not a collision
    confirmed = detector.update([a, b], tracker, "red")
    assert confirmed == []


def test_predicted_impact_scales_with_severity():
    low = predicted_impact("low", arrival_rate_pcu_per_min=5)
    high = predicted_impact("critical", arrival_rate_pcu_per_min=5)
    assert high["clearanceMinutes"] > low["clearanceMinutes"]
    assert high["predictedQueuePcu"] > low["predictedQueuePcu"]


def test_predicted_impact_no_delay_when_queue_under_capacity():
    result = predicted_impact("low", arrival_rate_pcu_per_min=0.5, lane_capacity_pcu=100)
    assert result["predictedDelayMin"] == 0
    assert result["congestionLevel"] == "low"
