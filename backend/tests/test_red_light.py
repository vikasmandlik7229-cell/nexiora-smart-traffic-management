"""Crossing-logic tests for RedLightDetector, using fake Detection objects
and positions instead of real video frames."""
from detection.detector import Detection
from violations.red_light import RedLightDetector

STOP_LINE_Y = 500


def make_det(track_id, y, class_name="car"):
    return Detection(
        track_id=track_id,
        class_name=class_name,
        confidence=0.9,
        bbox=(100, y - 40, 160, y),
        bottom_center=(130, y),
    )


def test_no_violation_on_first_sighting():
    det = RedLightDetector("lane1", STOP_LINE_Y)
    violations = det.update([make_det(1, 600)], "red")  # already past the line on first sighting
    assert violations == []


def test_violation_when_crossing_on_red():
    det = RedLightDetector("lane1", STOP_LINE_Y)
    det.update([make_det(1, 400)], "red")  # before the line
    violations = det.update([make_det(1, 520)], "red")  # now past it, still red
    assert len(violations) == 1
    assert violations[0].track_id == 1
    assert det.violation_count == 1


def test_no_violation_on_green_or_yellow():
    for state in ("green", "yellow"):
        det = RedLightDetector("lane1", STOP_LINE_Y)
        det.update([make_det(1, 400)], state)
        violations = det.update([make_det(1, 520)], state)
        assert violations == []


def test_track_flagged_only_once():
    det = RedLightDetector("lane1", STOP_LINE_Y)
    det.update([make_det(1, 400)], "red")
    first = det.update([make_det(1, 520)], "red")
    assert len(first) == 1
    # still moving, still red, same track - must not be flagged again
    second = det.update([make_det(1, 560)], "red")
    assert second == []
    assert det.violation_count == 1


def test_not_crossing_does_not_violate():
    det = RedLightDetector("lane1", STOP_LINE_Y)
    det.update([make_det(1, 300)], "red")
    violations = det.update([make_det(1, 350)], "red")  # moved, but never reached the line
    assert violations == []


def test_emergency_track_skipped():
    det = RedLightDetector("lane1", STOP_LINE_Y)
    det.update([make_det(1, 400)], "red")
    violations = det.update([make_det(1, 520)], "red", is_emergency_track=lambda tid: True)
    assert violations == []
    assert det.violation_count == 0
