"""Phase 7A: synthetic hourly traffic history for peak-hour prediction.

Generates 30 days of hourly vehicle counts per junction with a realistic
diurnal pattern (morning + evening peaks), lighter weekend traffic, and
random noise - clearly labelled as synthetic (CLAUDE.md section 10: honesty
about simulated vs real data). Real traffic_logs (once the database/Phase 4
exists) get merged in by train_peak.py, not here.

Run from backend/, with the venv active:
    python -m prediction.generate_hourly_data
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
CHARTS_DIR = HERE / "charts"
DAYS = 30
RNG = np.random.default_rng(seed=0)


def diurnal_base(hour: float) -> float:
    """Two bell curves for morning (~8am) and evening (~18:00) rush, plus a
    low daytime baseline and near-zero overnight."""
    morning = 40 * np.exp(-((hour - 8.5) ** 2) / (2 * 1.5 ** 2))
    evening = 55 * np.exp(-((hour - 18) ** 2) / (2 * 2.0 ** 2))
    daytime = 12 * np.exp(-((hour - 13) ** 2) / (2 * 4.0 ** 2))
    overnight_floor = 2
    return morning + evening + daytime + overnight_floor


def generate() -> pd.DataFrame:
    rows = []
    start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=DAYS)

    for junction in config.JUNCTIONS:
        jid = junction["id"]
        for day in range(DAYS):
            date = start + timedelta(days=day)
            day_of_week = date.weekday()  # 0 = Monday
            is_weekend = day_of_week >= 5
            weekend_factor = 0.6 if is_weekend else 1.0

            for hour in range(24):
                ts = date.replace(hour=hour)
                base = diurnal_base(hour) * weekend_factor
                noise = RNG.normal(0, base * 0.15 + 1)
                count = max(0, round(base + noise))
                rows.append({
                    "junctionId": jid,
                    "timestamp": ts.isoformat(),
                    "hour": hour,
                    "dayOfWeek": day_of_week,
                    "isWeekend": int(is_weekend),
                    "count": count,
                })

    return pd.DataFrame(rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    CHARTS_DIR.mkdir(exist_ok=True)

    df = generate()
    out_csv = DATA_DIR / "hourly_traffic.csv"
    df.to_csv(out_csv, index=False)
    print(f"Wrote {len(df)} rows ({DAYS} days x 24h x {len(config.JUNCTIONS)} junctions) to {out_csv}")

    fig, ax = plt.subplots(figsize=(9, 5))
    for is_weekend, label, style in ((0, "weekday", "-"), (1, "weekend", "--")):
        subset = df[df["isWeekend"] == is_weekend]
        by_hour = subset.groupby("hour")["count"].mean()
        ax.plot(by_hour.index, by_hour.values, style, label=label)
    ax.set_xlabel("hour of day")
    ax.set_ylabel("avg vehicle count")
    ax.set_title("Synthetic hourly traffic pattern (all junctions)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "hourly_pattern.png")
    print(f"Saved {CHARTS_DIR / 'hourly_pattern.png'}")


if __name__ == "__main__":
    main()
