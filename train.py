"""Train the next-calendar-month total expense forecaster.

Run from the repository root after generating ``data/transactions.csv`` and
``data/users.csv`` with ``scripts/make_dataset.py``.
"""
from __future__ import annotations

import json
import platform
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

SEED = 42
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ARTIFACT_DIR = ROOT / "artifacts"
FEATURES = [
    "lag_1", "lag_2", "lag_3", "lag_6", "lag_12", "roll_mean_3",
    "roll_mean_6", "roll_std_3", "trend", "n_months_history",
    "month_sin", "month_cos", "is_december", "is_january",
]
SCALED_FEATURES = FEATURES[:9]
SPLITS = {
    "train": ("2022-10", "2024-06"),
    "validation": ("2024-07", "2024-12"),
    "test": ("2025-01", "2025-06"),
}
TIERS = {"3-5": (3, 5), "6-11": (6, 11), "12+": (12, None)}
ML_MARGIN = 0.02  # absolute WAPE points; avoids selecting negligible wins.


def tier_for_history(n: int) -> str | None:
    if n < 3:
        return None
    if n <= 5:
        return "3-5"
    if n <= 11:
        return "6-11"
    return "12+"


def read_monthly_totals(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Validate inputs and create the complete per-user monthly time series."""
    tx_path, users_path = data_dir / "transactions.csv", data_dir / "users.csv"
    if not tx_path.exists() or not users_path.exists():
        raise FileNotFoundError("Run `python scripts/make_dataset.py --out data` first.")
    tx = pd.read_csv(tx_path, parse_dates=["date"])
    users = pd.read_csv(users_path, dtype={"user_id": str, "start_month": str})
    required_tx = {"user_id", "date", "amount", "note"}
    required_users = {"user_id", "start_month"}
    if not required_tx.issubset(tx) or not required_users.issubset(users):
        raise ValueError("Input CSV schema does not match the dataset generator output.")
    tx["user_id"] = tx["user_id"].astype(str)
    if tx["date"].isna().any() or (tx["amount"] <= 0).any():
        raise ValueError("Transactions must have valid dates and strictly positive expense amounts.")
    if users["user_id"].duplicated().any() or users["start_month"].isna().any():
        raise ValueError("users.csv must have one valid start_month per user.")
    users["start_month"] = pd.PeriodIndex(users["start_month"], freq="M")
    if not set(tx["user_id"]).issubset(set(users["user_id"])):
        raise ValueError("Every transaction user must exist in users.csv.")
    tx["month"] = tx["date"].dt.to_period("M")
    if (tx["month"] > pd.Period("2025-06", freq="M")).any():
        raise ValueError("Input contains transactions after the configured end month.")
    starts = users.set_index("user_id")["start_month"]
    if (tx["month"] < tx["user_id"].map(starts)).any():
        raise ValueError("Transactions occur before a user's declared first complete month.")

    summed = tx.groupby(["user_id", "month"], as_index=False)["amount"].sum()
    parts = []
    end = pd.Period("2025-06", freq="M")
    for row in users.sort_values("user_id").itertuples(index=False):
        months = pd.period_range(row.start_month, end, freq="M")
        one = pd.DataFrame({"user_id": str(row.user_id), "month": months})
        one = one.merge(summed, how="left", on=["user_id", "month"])
        one["total"] = one["amount"].fillna(0.0).astype(float)
        parts.append(one[["user_id", "month", "total"]])
    return pd.concat(parts, ignore_index=True)


def raw_feature_values(history: list[float] | np.ndarray, target_month: int) -> dict[str, float]:
    """Features before scale normalization; history excludes the target month."""
    h = np.asarray(history, dtype=float)
    n = len(h)
    def lag(k: int) -> float:
        return float(h[-k]) if n >= k else np.nan
    last3 = h[-3:] if n >= 3 else np.array([], dtype=float)
    mean3 = float(last3.mean()) if n >= 3 else np.nan
    mean6 = float(h[-6:].mean()) if n >= 6 else np.nan
    std3 = float(last3.std(ddof=0)) if n >= 3 else np.nan
    trend = mean3 - float(h[-6:-3].mean()) if n >= 6 else np.nan
    return {
        "lag_1": lag(1), "lag_2": lag(2), "lag_3": lag(3), "lag_6": lag(6),
        "lag_12": lag(12), "roll_mean_3": mean3, "roll_mean_6": mean6,
        "roll_std_3": std3, "trend": trend, "n_months_history": float(n),
        "month_sin": float(np.sin(2 * np.pi * target_month / 12)),
        "month_cos": float(np.cos(2 * np.pi * target_month / 12)),
        "is_december": float(target_month == 12), "is_january": float(target_month == 1),
    }


def feature_row(history: list[float] | np.ndarray, target_month: int) -> dict[str, float] | None:
    """Return the normalized model row, or None until three non-zero months exist."""
    values = raw_feature_values(history, target_month)
    scale = values["roll_mean_3"]
    if not np.isfinite(scale) or scale == 0:
        return None
    for name in SCALED_FEATURES:
        values[name] = values[name] / scale
    return values


def build_supervised(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for user_id, group in monthly.groupby("user_id", sort=True):
        group = group.sort_values("month")
        amounts = group["total"].to_numpy(float)
        months = group["month"].tolist()
        for i in range(3, len(group)):
            values = feature_row(amounts[:i], months[i].month)
            if values is None:
                continue
            # `feature_row` normalizes roll_mean_3 to 1, so preserve the
            # original scale separately for the normalized target.
            scale = float(np.mean(amounts[i - 3:i]))
            values.update({
                "user_id": user_id, "month": str(months[i]), "total": float(amounts[i]),
                "scale": scale,
                "target_normalized": float(amounts[i] / scale),
                "history_tier": tier_for_history(i), "n_months_history": i,
                "baseline_ma3": float(np.mean(amounts[i - 3:i])),
                "baseline_last": float(amounts[i - 1]),
                "baseline_seasonal": float(amounts[i - 12]) if i >= 12 else np.nan,
                "baseline_expanding": float(np.mean(amounts[:i])),
            })
            rows.append(values)
    result = pd.DataFrame(rows)
    result["month_period"] = pd.PeriodIndex(result["month"], freq="M")
    return result


def split_frame(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    start, end = (pd.Period(x, freq="M") for x in SPLITS[name])
    return frame.loc[frame["month_period"].between(start, end)].copy()


def make_candidates() -> list[tuple[str, Pipeline | HistGradientBoostingRegressor]]:
    candidates = []
    for alpha in (0.1, 1.0, 10.0):
        candidates.append((f"Ridge(alpha={alpha})", Pipeline([
            ("imputer", SimpleImputer(strategy="median")), ("model", Ridge(alpha=alpha))])))
    for leaves in (None, 12):
        candidates.append((f"RandomForest(max_leaf_nodes={leaves})", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(n_estimators=300, max_leaf_nodes=leaves,
             min_samples_leaf=2, random_state=SEED, n_jobs=1)),
        ])))
    for leaf_nodes in (7, 15):
        candidates.append((f"HistGradientBoosting(max_leaf_nodes={leaf_nodes})",
            HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05,
            max_leaf_nodes=leaf_nodes, l2_regularization=1.0, random_state=SEED)))
    return candidates


def wape(actual: np.ndarray, prediction: np.ndarray) -> float:
    denom = float(np.sum(np.abs(actual)))
    return float(np.sum(np.abs(actual - prediction)) / denom) if denom else np.nan


def metric_values(frame: pd.DataFrame, prediction: np.ndarray) -> dict[str, float]:
    actual = frame["total"].to_numpy(float)
    error = actual - prediction
    user_mae = pd.DataFrame({"user_id": frame["user_id"].to_numpy(), "abs_error": np.abs(error)}).groupby("user_id")["abs_error"].mean()
    return {
        "n_rows": int(len(frame)), "n_users": int(frame["user_id"].nunique()),
        "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
        "wape": wape(actual, prediction), "median_per_user_mae": float(user_mae.median()),
    }


def metrics_by_tier(frame: pd.DataFrame, prediction: np.ndarray, split: str, method: str) -> list[dict]:
    rows = []
    for tier in ("overall", *TIERS):
        mask = np.ones(len(frame), dtype=bool) if tier == "overall" else frame["history_tier"].eq(tier).to_numpy()
        if mask.any():
            rows.append({"split": split, "method": method, "history_tier": tier,
                         **metric_values(frame.loc[mask], prediction[mask])})
    return rows


def leakage_check(monthly: pd.DataFrame, supervised: pd.DataFrame) -> None:
    """Sample deterministically and recompute each row using only earlier totals."""
    sample = supervised.sample(n=min(25, len(supervised)), random_state=SEED)
    for row in sample.itertuples(index=False):
        prior = monthly[(monthly.user_id == row.user_id) & (monthly.month < pd.Period(row.month, freq="M"))]
        rebuilt = feature_row(prior.sort_values("month")["total"].to_numpy(float), pd.Period(row.month, freq="M").month)
        assert rebuilt is not None
        for feature in FEATURES:
            assert np.isclose(rebuilt[feature], getattr(row, feature), equal_nan=True), f"leakage check failed: {feature}"


def write_metrics(rows: list[dict], selected_name: str, tier_methods: dict[str, str]) -> None:
    metrics = pd.DataFrame(rows)
    metrics.to_csv(ARTIFACT_DIR / "metrics.csv", index=False, float_format="%.12f")
    test = metrics[metrics["split"].eq("test")]
    ml_tiers = [tier for tier, method in tier_methods.items() if method == "ml"]
    selection_statement = (
        "ML beat the 3-month moving average by the required margin for: " + ", ".join(ml_tiers) + "."
        if ml_tiers else
        "ML did not beat the 3-month moving average by the required margin in any history tier; production uses the moving average throughout."
    )
    lines = [
        "# Next-month total expense forecast metrics", "",
        f"Selected ML candidate: `{selected_name}`.",
        "", "The deployment gate requires an absolute validation-WAPE improvement of at least 0.020 (two percentage points) over the 3-month moving average. This margin treats tiny validation changes as noise.",
        "", selection_statement,
        "", "## Chosen method by history tier", "",
        "| Tier | Production method |", "|---|---|",
    ]
    lines.extend(f"| {tier} | {tier_methods[tier]} |" for tier in TIERS)
    lines += ["", "## Test metrics", "", "| Method | Tier | Rows | MAE | RMSE | WAPE | Median per-user MAE |", "|---|---|---:|---:|---:|---:|---:|"]
    for r in test.itertuples(index=False):
        lines.append(f"| {r.method} | {r.history_tier} | {r.n_rows} | {r.mae:.2f} | {r.rmse:.2f} | {r.wape:.4f} | {r.median_per_user_mae:.2f} |")
    (ARTIFACT_DIR / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    monthly = read_monthly_totals()
    monthly.assign(month=monthly["month"].astype(str)).to_csv(ARTIFACT_DIR / "monthly_totals.csv", index=False, float_format="%.2f")
    supervised = build_supervised(monthly)
    leakage_check(monthly, supervised)
    train, validation, test = (split_frame(supervised, key) for key in SPLITS)
    x_train, y_train = train[FEATURES], train["target_normalized"]
    x_val, y_val = validation[FEATURES], validation["target_normalized"]

    candidate_scores = []
    for name, model in make_candidates():
        model.fit(x_train, y_train)
        pred = np.maximum(0.0, model.predict(x_val) * validation["scale"].to_numpy(float))
        candidate_scores.append((wape(validation["total"].to_numpy(float), pred), name, model))
    _, selected_name, selected_validation_model = min(candidate_scores, key=lambda item: item[0])
    val_ml_pred = np.maximum(0.0, selected_validation_model.predict(x_val) * validation["scale"].to_numpy(float))

    tier_methods = {}
    for tier in TIERS:
        part = validation[validation["history_tier"].eq(tier)]
        ix = part.index.to_numpy()
        positions = validation.index.get_indexer(ix)
        baseline_score = wape(part["total"].to_numpy(float), part["baseline_ma3"].to_numpy(float))
        ml_score = wape(part["total"].to_numpy(float), val_ml_pred[positions])
        tier_methods[tier] = "ml" if np.isfinite(ml_score) and baseline_score - ml_score >= ML_MARGIN else "moving_average_3"

    combined = pd.concat([train, validation], ignore_index=True)
    final_model = dict(make_candidates())[selected_name]
    final_model.fit(combined[FEATURES], combined["target_normalized"])
    test_ml_pred = np.maximum(0.0, final_model.predict(test[FEATURES]) * test["scale"].to_numpy(float))
    deployed_pred = test["baseline_ma3"].to_numpy(float).copy()
    for tier in TIERS:
        mask = test["history_tier"].eq(tier).to_numpy()
        if tier_methods[tier] == "ml":
            deployed_pred[mask] = test_ml_pred[mask]

    metric_rows = []
    for method, pred in {
        "moving_average_3": test["baseline_ma3"].to_numpy(float),
        "last_month": test["baseline_last"].to_numpy(float),
        "seasonal_naive": test["baseline_seasonal"].to_numpy(float),
        "expanding_mean": test["baseline_expanding"].to_numpy(float),
        "selected_ml": test_ml_pred, "deployed_tiered": deployed_pred,
    }.items():
        valid = np.isfinite(pred)
        if valid.any():
            metric_rows.extend(metrics_by_tier(test.loc[valid], pred[valid], "test", method))
    write_metrics(metric_rows, selected_name, tier_methods)
    joblib.dump(final_model, ARTIFACT_DIR / "model.joblib")
    meta = {
        "feature_list": FEATURES, "seed": SEED, "training_dates": {"train": list(SPLITS["train"]), "validation": list(SPLITS["validation"])},
        "split_dates": SPLITS, "test_dates": list(SPLITS["test"]), "selected_ml_candidate": selected_name,
        "selection_margin_absolute_wape": ML_MARGIN, "chosen_method_per_tier": tier_methods,
        "metrics": metric_rows,
        "library_versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__},
        "run_date": date.today().isoformat(),
        "validation_wape": {"selected_ml": wape(validation["total"].to_numpy(float), val_ml_pred), "moving_average_3": wape(validation["total"].to_numpy(float), validation["baseline_ma3"].to_numpy(float))},
    }
    (ARTIFACT_DIR / "model_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Saved artifacts for {len(monthly.user_id.unique())} users; selected {selected_name}.")
    print("Tier methods:", tier_methods)


if __name__ == "__main__":
    main()
