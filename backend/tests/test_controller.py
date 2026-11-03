"""Safety-rule tests for SignalController: single green, MIN/MAX green bounds,
no starvation, yellow always before red (including pre-emption and manual
overrides), and override duration capped.

Uses a fake clock (monkeypatched time.time) instead of real sleeps, since the
controller is driven entirely by wall-clock comparisons.
"""
import time

import pytest

import config
from signals.controller import GREEN, YELLOW, SignalController

LANES = ["lane1", "lane2", "lane3", "lane4"]


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fc = FakeClock()
    monkeypatch.setattr(time, "time", fc.time)
    return fc


def make_controller():
    return SignalController("TEST", LANES)


def test_only_one_green_or_yellow_ever(clock):
    ctrl = make_controller()
    loads = {"lane1": 5, "lane2": 2, "lane3": 0, "lane4": 1}
    for _ in range(300):
        ctrl.tick(loads)
        active = [l for l in LANES if ctrl.lane_state(l) in (GREEN, YELLOW)]
        assert len(active) <= 1
        clock.advance(1)


def test_green_within_min_and_max(clock):
    ctrl = make_controller()
    ctrl.tick({"lane1": 1000, "lane2": 0, "lane3": 0, "lane4": 0})
    duration = ctrl.phase_ends_at - time.time()
    assert config.MIN_GREEN <= duration <= config.MAX_GREEN

    ctrl2 = make_controller()
    ctrl2.tick({l: 0 for l in LANES})
    duration2 = ctrl2.phase_ends_at - time.time()
    assert duration2 >= config.MIN_GREEN


def test_starved_empty_lane_eventually_served(clock):
    ctrl = make_controller()
    loads = {"lane1": 10, "lane2": 0, "lane3": 0, "lane4": 0}
    ctrl.tick(loads)
    assert ctrl.active_lane == "lane1"

    served_lanes = set()
    for _ in range(400):
        clock.advance(1)
        ctrl.tick(loads)
        served_lanes.add(ctrl.active_lane)
    assert len(served_lanes) > 1, "an empty lane waiting past MAX_WAIT must be served"


def test_empty_lane_skipped_before_starving(clock):
    ctrl = make_controller()
    loads = {"lane1": 10, "lane2": 0, "lane3": 0, "lane4": 0}
    ctrl.tick(loads)
    for _ in range(int(config.MAX_WAIT) - 5):
        clock.advance(1)
        ctrl.tick(loads)
    assert ctrl.active_lane == "lane1"


def test_yellow_before_red_on_normal_cycle(clock):
    ctrl = make_controller()
    loads = {"lane1": 5, "lane2": 5, "lane3": 0, "lane4": 0}
    ctrl.tick(loads)
    first_lane = ctrl.active_lane

    duration = ctrl.phase_ends_at - time.time()
    clock.advance(duration - 0.5)
    ctrl.tick(loads)
    assert ctrl.lane_state(first_lane) == GREEN

    clock.advance(1)
    ctrl.tick(loads)
    assert ctrl.lane_state(first_lane) == YELLOW


def test_yellow_before_red_on_emergency_preempt(clock):
    ctrl = make_controller()
    loads = {l: 5 for l in LANES}
    ctrl.tick(loads)
    first_lane = ctrl.active_lane
    other_lane = next(l for l in LANES if l != first_lane)

    ctrl.set_emergency(other_lane)
    assert ctrl.lane_state(first_lane) == YELLOW, "must pass through yellow, never straight to a new green"

    clock.advance(config.YELLOW_TIME + 0.1)
    ctrl.tick(loads)
    assert ctrl.active_lane == other_lane
    assert ctrl.lane_state(other_lane) == GREEN

    # emergency holds the lane green even past its computed duration
    clock.advance(config.MAX_GREEN + 10)
    ctrl.tick(loads)
    assert ctrl.active_lane == other_lane
    assert ctrl.lane_state(other_lane) == GREEN

    # clearing emergency releases the hold via yellow, not straight to red
    ctrl.set_emergency(None)
    assert ctrl.lane_state(other_lane) == YELLOW


def test_yellow_before_red_on_force_green(clock):
    ctrl = make_controller()
    loads = {l: 5 for l in LANES}
    ctrl.tick(loads)
    first_lane = ctrl.active_lane
    other_lane = next(l for l in LANES if l != first_lane)

    ctrl.force_green(other_lane, 20)
    assert ctrl.lane_state(first_lane) == YELLOW

    clock.advance(config.YELLOW_TIME + 0.1)
    ctrl.tick(loads)
    assert ctrl.active_lane == other_lane
    assert ctrl.lane_state(other_lane) == GREEN


def test_override_capped_at_max_override_seconds(clock):
    ctrl = make_controller()
    ctrl.tick({l: 0 for l in LANES})
    lane = ctrl.active_lane

    ctrl.force_green(lane, config.MAX_OVERRIDE_SECONDS + 1000)
    duration = ctrl.phase_ends_at - time.time()
    assert duration <= config.MAX_OVERRIDE_SECONDS


def test_release_ends_override_via_yellow(clock):
    ctrl = make_controller()
    ctrl.tick({l: 0 for l in LANES})
    lane = ctrl.active_lane

    ctrl.force_green(lane, 50)
    ctrl.release()
    assert ctrl.lane_state(lane) == YELLOW


def test_blocked_lane_never_selected(clock):
    ctrl = make_controller()
    ctrl.block_lane("lane1")
    loads = {"lane1": 1000, "lane2": 1, "lane3": 0, "lane4": 0}
    for _ in range(200):
        ctrl.tick(loads)
        assert ctrl.active_lane != "lane1"
        clock.advance(1)


def test_all_lanes_blocked_holds_red_instead_of_greening_a_blocked_lane(clock):
    """Every approach blocked at once (e.g. simultaneous accidents) must
    never turn a blocked lane green - better to hold everything red."""
    ctrl = make_controller()
    for lane in LANES:
        ctrl.block_lane(lane)
    loads = {"lane1": 10, "lane2": 10, "lane3": 10, "lane4": 10}
    for _ in range(50):
        ctrl.tick(loads)
        assert ctrl.active_lane is None
        for lane in LANES:
            assert ctrl.lane_state(lane) == "red"
        clock.advance(1)

    # Unblocking one lane lets the controller recover and go green again.
    ctrl.unblock_lane("lane2")
    ctrl.tick(loads)
    assert ctrl.active_lane == "lane2"
    assert ctrl.lane_state("lane2") == GREEN
