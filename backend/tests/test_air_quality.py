"""Tests for AQI labelling and the eco-mode switch. Uses fake controller/
client objects rather than a real database connection or OpenWeather call.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airquality.aqi import AQI_LABELS, ECO_ALERT_COOLDOWN_S, EcoModeManager, simulated_aqi


class FakeController:
    def __init__(self):
        self.eco_calls = []

    def set_eco(self, enabled):
        self.eco_calls.append(enabled)


class FakeClient:
    def __init__(self):
        self.alerts = []

    def add_alert(self, data):
        self.alerts.append(data)


def test_simulated_aqi_is_in_valid_range():
    for _ in range(20):
        reading = simulated_aqi()
        assert 1 <= reading["aqi"] <= 5
        assert reading["label"] == AQI_LABELS[reading["aqi"]]
        assert reading["source"] == "simulated"


def test_eco_mode_engages_at_aqi_4_and_above():
    manager = EcoModeManager()
    controller = FakeController()
    client = FakeClient()

    manager.apply("J1", aqi=4, controller=controller, client=client)
    assert controller.eco_calls == [True]
    assert len(client.alerts) == 1
    assert client.alerts[0]["type"] == "air"


def test_eco_mode_not_engaged_below_threshold():
    manager = EcoModeManager()
    controller = FakeController()
    client = FakeClient()

    manager.apply("J1", aqi=3, controller=controller, client=client)
    assert controller.eco_calls == [False]
    assert client.alerts == []


def test_eco_mode_releases_when_aqi_improves():
    manager = EcoModeManager()
    controller = FakeController()
    client = FakeClient()

    manager.apply("J1", aqi=5, controller=controller, client=client)
    manager.apply("J1", aqi=2, controller=controller, client=client)
    assert controller.eco_calls == [True, False]


def test_eco_alert_fires_only_once_per_cooldown(monkeypatch):
    manager = EcoModeManager()
    controller = FakeController()
    client = FakeClient()

    t = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    manager.apply("J1", aqi=4, controller=controller, client=client)
    manager.apply("J1", aqi=3, controller=controller, client=client)  # eco off
    manager.apply("J1", aqi=4, controller=controller, client=client)  # eco on again, same hour
    assert len(client.alerts) == 1  # second re-trigger within the cooldown window is suppressed

    t[0] += ECO_ALERT_COOLDOWN_S + 1
    manager.apply("J1", aqi=3, controller=controller, client=client)
    manager.apply("J1", aqi=4, controller=controller, client=client)  # past cooldown - new alert allowed
    assert len(client.alerts) == 2


def test_eco_mode_is_per_junction():
    manager = EcoModeManager()
    ctrl_a, ctrl_b = FakeController(), FakeController()
    client = FakeClient()

    manager.apply("J1", aqi=5, controller=ctrl_a, client=client)
    manager.apply("J2", aqi=1, controller=ctrl_b, client=client)
    assert ctrl_a.eco_calls == [True]
    assert ctrl_b.eco_calls == [False]
