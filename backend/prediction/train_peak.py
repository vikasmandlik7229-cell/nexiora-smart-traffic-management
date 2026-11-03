"""Phase 7A: train peak-hour predictors (Linear Regression vs Random Forest)
on the synthetic hourly data, merging in real traffic_logs if a CSV export
of them exists yet (none does until Phase 4/the database is live - synthetic
only for now, see CLAUDE.md section 10).

Run from backend/, with the venv active, after generate_hourly_data.py:
    python -m prediction.train_peak
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
MODELS_DIR = HERE / "models"
CHARTS_DIR = HERE / "charts"

FEATURE_COLUMNS = ["hour_sin", "hour_cos", "dayOfWeek", "isWeekend"]


def add_cyclical_hour(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return df


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "hourly_traffic.csv")

    real_logs_csv = DATA_DIR / "traffic_logs_export.csv"
    if real_logs_csv.exists():
        real = pd.read_csv(real_logs_csv)
        df = pd.concat([df, real], ignore_index=True)
        print(f"Merged {len(real)} real traffic_logs rows (Phase 4 database export found).")
    else:
        print("No real traffic_logs export found yet - training on synthetic data only.")

    return add_cyclical_hour(df)


def build_features(df: pd.DataFrame, encoder: OneHotEncoder = None):
    junction_ids = df[["junctionId"]]
    if encoder is None:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        junction_encoded = encoder.fit_transform(junction_ids)
    else:
        junction_encoded = encoder.transform(junction_ids)

    numeric = df[FEATURE_COLUMNS].to_numpy()
    X = np.hstack([numeric, junction_encoded])
    return X, encoder


def main():
    MODELS_DIR.mkdir(exist_ok=True)
    CHARTS_DIR.mkdir(exist_ok=True)

    df = load_data()
    X, encoder = build_features(df)
    y = df["count"].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)

    models = {
        "linear_regression": LinearRegression(),
        "random_forest": RandomForestRegressor(n_estimators=200, max_depth=10, random_state=0),
    }

    results = {}
    predictions = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        predictions[name] = pred
        results[name] = {
            "mae": float(mean_absolute_error(y_test, pred)),
            "rmse": float(mean_squared_error(y_test, pred) ** 0.5),
            "r2": float(r2_score(y_test, pred)),
        }

    print("\nModel comparison (lower MAE/RMSE better, higher R2 better):")
    for name, m in results.items():
        print(f"  {name:18s} MAE={m['mae']:.2f}  RMSE={m['rmse']:.2f}  R2={m['r2']:.3f}")

    best_name = max(results, key=lambda n: results[n]["r2"])
    best_model = models[best_name]
    print(f"\nBest model: {best_name} (R2={results[best_name]['r2']:.3f})")

    joblib.dump({"model": best_model, "encoder": encoder, "feature_columns": FEATURE_COLUMNS},
                MODELS_DIR / "peak_model.joblib")
    (MODELS_DIR / "peak_metrics.json").write_text(json.dumps({
        "results": results,
        "bestModel": best_name,
    }, indent=2))
    print(f"Saved {MODELS_DIR / 'peak_model.joblib'} and peak_metrics.json")

    # --- charts ---
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_test, predictions[best_name], alpha=0.3, s=10)
    lims = [0, max(y_test.max(), predictions[best_name].max())]
    ax.plot(lims, lims, "r--", linewidth=1)
    ax.set_xlabel("actual count")
    ax.set_ylabel("predicted count")
    ax.set_title(f"Actual vs predicted ({best_name})")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "peak_actual_vs_predicted.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    names = list(results.keys())
    ax.bar(names, [results[n]["mae"] for n in names])
    ax.set_ylabel("MAE")
    ax.set_title("Peak-hour model comparison")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "peak_model_comparison.png")

    if best_name == "random_forest":
        importances = best_model.feature_importances_
        feature_names = FEATURE_COLUMNS + list(encoder.get_feature_names_out(["junctionId"]))
        fig, ax = plt.subplots(figsize=(7, 4))
        order = np.argsort(importances)[::-1]
        ax.bar([feature_names[i] for i in order], importances[order])
        ax.set_ylabel("importance")
        ax.set_title("Random Forest feature importance")
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / "peak_feature_importance.png")

    print(f"Saved charts to {CHARTS_DIR}")


if __name__ == "__main__":
    main()
