"""Phase 10: aggregates traffic_logs, metrics, violations, emergency_trips,
accidents and air_quality_logs for a date (or range) into a
`daily_reports` doc, a PDF with captioned charts, and CSV exports.

Handles missing data gracefully (college-project scale, not a production
analytics pipeline): any empty dataset just gets skipped with a note rather
than crashing the report.

Run from backend/, with the venv active:
    python -m reports.daily_report --demo-data        # fill 1 week of labelled demo records first
    python -m reports.daily_report --date 2026-10-29
    python -m reports.daily_report --range 2026-10-23 2026-10-29
"""
import argparse
import csv
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import config
from db.sql_client import get_client

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
AQI_LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}


def _date_list(start: str, end: str):
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    days, d = [], d0
    while d <= d1:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def _in_range(ts, dates_set):
    if not ts:
        return False
    try:
        return datetime.fromtimestamp(ts).date().isoformat() in dates_set
    except (OSError, OverflowError, ValueError):
        return False


def _date_bounds(dates):
    """Local-midnight epoch bounds [start, end) covering every date in
    `dates` (assumed contiguous, as produced by _date_list)."""
    ordered = sorted(dates)
    start = datetime.strptime(ordered[0], "%Y-%m-%d")
    end = datetime.strptime(ordered[-1], "%Y-%m-%d") + timedelta(days=1)
    return start.timestamp(), end.timestamp()


def _fetch_in_range(client, collection, dates):
    """Range-filters server-side via the SQLite client's `ts` column instead
    of fetching the whole collection and filtering in Python -
    violations/accidents/aqi_logs/trips grow without bound over the
    project's lifetime, so an unfiltered fetch would re-read every document
    ever written on every report run."""
    start_ts, end_ts = _date_bounds(dates)
    return client.query_range(collection, start_ts, end_ts)


def aggregate(dates):
    client = get_client()
    if not client.enabled:
        print("Database not connected - nothing to aggregate.")
        return None

    dates_set = set(dates)
    # metrics doc ids are "{junctionId}_{date}" (no numeric timestamp field),
    # and the collection stays small (junctions x days) even over a long
    # project lifetime, so a full fetch here is fine.
    metrics = [m for m in client.list_all("metrics") if m["id"].rsplit("_", 1)[-1] in dates_set]
    violations = _fetch_in_range(client, "violations", dates)
    trips = _fetch_in_range(client, "emergency_trips", dates)
    accidents = _fetch_in_range(client, "accidents", dates)
    aqi_logs = _fetch_in_range(client, "air_quality_logs", dates)

    return {"metrics": metrics, "violations": violations, "trips": trips,
            "accidents": accidents, "aqiLogs": aqi_logs}


def summarize(data: dict) -> dict:
    metrics = data["metrics"]
    aqi_logs = data["aqiLogs"]
    avg_aqi = mean([a.get("aqi", 0) for a in aqi_logs]) if aqi_logs else None

    summary = {
        "Avg wait, adaptive (s)": f"{mean([m.get('avgWaitAdaptiveS', 0) for m in metrics]):.1f}" if metrics else "no data",
        "Avg wait, fixed-time (s)": f"{mean([m.get('avgWaitFixedS', 0) for m in metrics]):.1f}" if metrics else "no data",
        "Total fuel saved (L)": f"{sum(m.get('fuelSavedL', 0) for m in metrics):.2f}" if metrics else "no data",
        "Total CO2 saved (kg)": f"{sum(m.get('co2SavedKg', 0) for m in metrics):.2f}" if metrics else "no data",
        "Red-light violations": str(len(data["violations"])),
        "Ambulance trips": str(len(data["trips"])),
        "Avg ambulance travel time (s)": f"{mean([t.get('travelTimeS', 0) for t in data['trips']]):.1f}" if data["trips"] else "no data",
        "Accidents recorded": str(len(data["accidents"])),
        "Avg AQI": f"{avg_aqi:.1f} ({AQI_LABELS.get(round(avg_aqi), 'n/a')})" if avg_aqi is not None else "no data",
    }
    return summary


def make_charts(data: dict, charts_dir: Path) -> list:
    charts_dir.mkdir(parents=True, exist_ok=True)
    charts = []

    if data["metrics"]:
        fig, ax = plt.subplots(figsize=(8, 4))
        by_junction = {}
        for m in data["metrics"]:
            jid = m["id"].rsplit("_", 1)[0]
            by_junction.setdefault(jid, []).append(m)
        junctions = sorted(by_junction)
        adaptive = [mean([m.get("avgWaitAdaptiveS", 0) for m in by_junction[j]]) for j in junctions]
        fixed = [mean([m.get("avgWaitFixedS", 0) for m in by_junction[j]]) for j in junctions]
        x = range(len(junctions))
        ax.bar([i - 0.2 for i in x], adaptive, 0.4, label="adaptive")
        ax.bar([i + 0.2 for i in x], fixed, 0.4, label="fixed-time")
        ax.set_xticks(list(x))
        ax.set_xticklabels(junctions)
        ax.set_ylabel("avg wait (s)")
        ax.set_title("Adaptive vs fixed-time wait, per junction")
        ax.legend()
        fig.tight_layout()
        path = charts_dir / "wait_comparison.png"
        fig.savefig(path)
        plt.close(fig)
        charts.append((path, "Average waiting time: adaptive signal control vs a fixed-time baseline."))

    if data["violations"]:
        fig, ax = plt.subplots(figsize=(8, 4))
        by_lane = {}
        for v in data["violations"]:
            by_lane[v.get("laneId", "?")] = by_lane.get(v.get("laneId", "?"), 0) + 1
        ax.bar(list(by_lane.keys()), list(by_lane.values()))
        ax.set_ylabel("violations")
        ax.set_title("Red-light violations by lane")
        fig.tight_layout()
        path = charts_dir / "violations_by_lane.png"
        fig.savefig(path)
        plt.close(fig)
        charts.append((path, "Red-light violations captured, grouped by lane."))

    if data["aqiLogs"]:
        fig, ax = plt.subplots(figsize=(8, 4))
        sorted_logs = sorted(data["aqiLogs"], key=lambda a: a.get("timestamp", 0))
        times = [datetime.fromtimestamp(a["timestamp"]) for a in sorted_logs if a.get("timestamp")]
        values = [a.get("aqi", 0) for a in sorted_logs if a.get("timestamp")]
        ax.plot(times, values, marker="o", markersize=3)
        ax.set_ylabel("AQI (1=Good, 5=Very Poor)")
        ax.set_title("Air quality trend")
        fig.autofmt_xdate()
        fig.tight_layout()
        path = charts_dir / "aqi_trend.png"
        fig.savefig(path)
        plt.close(fig)
        charts.append((path, "Air Quality Index over the reporting period."))

    return charts


def write_csvs(data: dict, out_dir: Path, label: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        if not rows:
            continue
        path = out_dir / f"{label}_{name}.csv"
        fieldnames = sorted({k for row in rows for k in row.keys()})
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  wrote {path}")


def build_pdf(dates: list, summary: dict, charts: list, out_path: Path):
    doc = SimpleDocTemplate(str(out_path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Nexiora Smart Traffic Management", styles["Title"]),
        Paragraph(f"Daily Report: {dates[0]}" + (f" to {dates[-1]}" if len(dates) > 1 else ""), styles["Heading2"]),
        Spacer(1, 1 * cm),
    ]

    table_data = [["Metric", "Value"]] + [[k, v] for k, v in summary.items() if k != "Days covered"]
    table = Table(table_data, colWidths=[9 * cm, 7 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story += [table, Spacer(1, 1 * cm)]

    if not charts:
        story.append(Paragraph("No chart-worthy data was available for this period.", styles["Italic"]))

    for chart_path, caption in charts:
        story.append(RLImage(str(chart_path), width=15 * cm, height=7.5 * cm))
        story.append(Paragraph(caption, styles["Italic"]))
        story.append(Spacer(1, 0.6 * cm))

    doc.build(story)
    print(f"Saved PDF to {out_path}")


def generate_demo_data(days: int = 7):
    client = get_client()
    if not client.enabled:
        print("Database not connected - cannot generate demo data.")
        return

    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        day_start = time.mktime(d.timetuple())

        for j in config.JUNCTIONS:
            adaptive = random.uniform(15, 35)
            fixed = adaptive * random.uniform(1.5, 2.5)
            client.write_metrics(j["id"], d_str, {
                "avgWaitAdaptiveS": adaptive, "avgWaitFixedS": fixed,
                "waitReductionPct": (fixed - adaptive) / fixed * 100,
                "idleVehicleSecondsSaved": random.uniform(500, 2000),
                "fuelSavedL": random.uniform(0.5, 3), "co2SavedKg": random.uniform(1, 7),
            })
            aqi = random.randint(1, 4)
            client.add_air_quality_log({
                "junctionId": j["id"], "aqi": aqi, "label": AQI_LABELS[aqi],
                "pm2_5": random.uniform(10, 80), "pm10": random.uniform(20, 120),
                "no2": random.uniform(10, 60), "co": random.uniform(200, 900),
                "source": "demo", "timestamp": day_start + 43200,
            })

        for _ in range(random.randint(0, 4)):
            client.add_violation({
                "junctionId": "J1", "laneId": random.choice(["lane1", "lane2", "lane3", "lane4"]),
                "trackId": random.randint(1, 999), "vehicleType": random.choice(["car", "bike", "truck"]),
                "imageFile": None, "cropFile": None, "timestamp": day_start + random.uniform(0, 86400),
            })

        if random.random() < 0.3:
            start_ts = day_start + random.uniform(0, 86400)
            client.add_emergency_trip({
                "vehicleId": "AMB001", "startedAt": start_ts, "endedAt": start_ts + random.uniform(200, 400),
                "travelTimeS": random.uniform(200, 400), "junctionsPreempted": ["J1", "J2"],
            })

        if random.random() < 0.15:
            ts = day_start + random.uniform(0, 86400)
            client.write_accident(f"demo_{d_str}_{random.randint(1, 999)}", {
                "junctionId": "J2", "roadId": None, "laneId": None, "method": "demo",
                "severity": random.choice(["low", "medium", "high"]), "status": "resolved",
                "detectedAt": ts, "resolvedAt": ts + 900, "predictedQueue": random.uniform(10, 50),
                "predictedDelayMin": random.uniform(0, 20), "alternativeRoutes": [],
            })

    time.sleep(3)  # let the write queue flush before this one-shot script exits
    print(f"Demo data generated for the past {days} days (clearly labelled source='demo').")


def run_report(dates: list):
    data = aggregate(dates)
    if data is None:
        return

    summary = summarize(data)
    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    label = dates[0] if len(dates) == 1 else f"{dates[0]}_to_{dates[-1]}"
    charts_dir = OUTPUT_DIR / "charts"
    charts = make_charts(data, charts_dir)
    write_csvs(data, OUTPUT_DIR, label)
    pdf_path = OUTPUT_DIR / f"report_{label}.pdf"
    build_pdf(dates, summary, charts, pdf_path)

    client = get_client()
    if client.enabled:
        client.write_daily_report(label, {
            "summary": summary,
            "pdfFile": pdf_path.name,
            "csvFiles": [p.name for p in OUTPUT_DIR.glob(f"{label}_*.csv")],
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"), help="YYYY-MM-DD YYYY-MM-DD")
    parser.add_argument("--demo-data", action="store_true", help="fill 1 week of labelled demo records first")
    args = parser.parse_args()

    if args.demo_data:
        generate_demo_data()

    if args.range:
        dates = _date_list(*args.range)
    elif args.date:
        dates = [args.date]
    else:
        dates = [date.today().isoformat()]

    run_report(dates)


if __name__ == "__main__":
    main()
