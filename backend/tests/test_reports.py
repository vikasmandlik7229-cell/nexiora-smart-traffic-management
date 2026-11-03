"""Tests for the date-handling and summarization helpers in daily_report.py
that don't need a live Firestore connection.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports.daily_report import _date_list, _in_range, summarize


def test_date_list_single_day():
    assert _date_list("2026-01-01", "2026-01-01") == ["2026-01-01"]


def test_date_list_spans_days():
    assert _date_list("2026-01-01", "2026-01-03") == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_in_range_true_for_matching_date():
    ts = time.mktime(datetime(2026, 1, 2, 14, 30).timetuple())
    assert _in_range(ts, {"2026-01-02"}) is True


def test_in_range_false_for_other_date():
    ts = time.mktime(datetime(2026, 1, 5, 14, 30).timetuple())
    assert _in_range(ts, {"2026-01-02"}) is False


def test_in_range_handles_none():
    assert _in_range(None, {"2026-01-02"}) is False


def test_summarize_handles_empty_data():
    empty = {"metrics": [], "violations": [], "trips": [], "accidents": [], "aqiLogs": []}
    summary = summarize(empty)
    assert summary["Avg wait, adaptive (s)"] == "no data"
    assert summary["Red-light violations"] == "0"
    assert summary["Avg AQI"] == "no data"


def test_summarize_computes_averages():
    data = {
        "metrics": [{"avgWaitAdaptiveS": 10, "avgWaitFixedS": 20, "fuelSavedL": 1, "co2SavedKg": 2},
                    {"avgWaitAdaptiveS": 20, "avgWaitFixedS": 30, "fuelSavedL": 1, "co2SavedKg": 2}],
        "violations": [{}, {}, {}],
        "trips": [{"travelTimeS": 100}],
        "accidents": [],
        "aqiLogs": [{"aqi": 2}, {"aqi": 4}],
    }
    summary = summarize(data)
    assert summary["Avg wait, adaptive (s)"] == "15.0"
    assert summary["Red-light violations"] == "3"
    assert summary["Total fuel saved (L)"] == "2.00"
    assert "3.0" in summary["Avg AQI"]
