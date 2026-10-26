import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import predictor
import train

ROOT = Path(__file__).resolve().parents[1]


def test_leakage_check_passes():
    monthly = train.read_monthly_totals()
    train.leakage_check(monthly, train.build_supervised(monthly))


def test_training_is_deterministic():
    subprocess.run([sys.executable, "train.py"], cwd=ROOT, check=True)
    first = (ROOT / "artifacts" / "metrics.csv").read_bytes()
    subprocess.run([sys.executable, "train.py"], cwd=ROOT, check=True)
    assert (ROOT / "artifacts" / "metrics.csv").read_bytes() == first


def test_predictor_matches_saved_deployed_predictions_for_five_users():
    monthly = train.read_monthly_totals()
    supervised = train.build_supervised(monthly)
    test = train.split_frame(supervised, "test")
    meta = json.loads((ROOT / "artifacts" / "model_meta.json").read_text())
    model = __import__("joblib").load(ROOT / "artifacts" / "model.joblib")
    for row in test.groupby("user_id", sort=True).head(1).head(5).itertuples(index=False):
        prior = monthly[(monthly.user_id == row.user_id) & (monthly.month < pd.Period(row.month, freq="M"))].sort_values("month")
        history = prior.total.tolist()
        expected = row.baseline_ma3
        tier = train.tier_for_history(len(history))
        if meta["chosen_method_per_tier"][tier] == "ml":
            expected = float(model.predict(pd.DataFrame([dict(zip(train.FEATURES, [getattr(row, f) for f in train.FEATURES]))]))[0] * row.scale)
            expected = max(0.0, expected)
        assert predictor.predict_next_month(history, pd.Period(row.month, freq="M").month) == pytest.approx(expected, abs=1e-6)


def test_predictor_handles_required_history_lengths():
    assert predictor.predict_next_month([], 1) == 0.0
    assert predictor.predict_next_month([50], 2) == 50.0
    assert predictor.predict_next_month([20, 40], 3) == 30.0
    assert np.isfinite(predictor.predict_next_month([10, 20, 30], 4))
    assert np.isfinite(predictor.predict_next_month([10.0] * 12, 5))
