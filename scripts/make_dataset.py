#!/usr/bin/env python3
"""Generate a minimal synthetic expense dataset for monthly expense forecasting.

One command:
    python make_dataset.py                       # defaults: 50 users, 36 months
    python make_dataset.py --customers 100 --out ./data

What it does:
    1. Clones mbazouz/synthetic-bank-dataset (pinned commit, needs git + internet)
    2. Generates raw synthetic banking data with it
    3. Writes two simple CSVs to --out:
         transactions.csv : user_id, date, amount, note        (expenses only)
         users.csv        : user_id, start_month                (first complete month)

Notes:
    - Only ordinary spending is kept (card purchases and ATM cash). Income,
      internal transfers, loan payments and bank/overdraft fees are excluded.
    - Each user's partial first month is dropped, so every month in the files is complete.
      A month with no rows for a user (between start_month and the end) means zero spending.
    - Data is 100% synthetic (US-style merchants, USD). The generator is licensed
      PolyForm Noncommercial 1.0.0: fine for coursework, cite the repo, no commercial use.

Requires: Python 3.10+, git, and: pip install pandas numpy faker pyarrow tqdm
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/mbazouz/synthetic-bank-dataset.git"
PINNED_COMMIT = "7418fa18ebc261c81a0133ead633d63e84a03cf9"  # tested version (2026-10-11)


def run(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"Command failed: {' '.join(map(str, cmd))}\n{res.stderr[-1500:]}")
    return res.stdout


def check_deps():
    missing = []
    for mod in ("pandas", "numpy", "faker", "pyarrow", "tqdm"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.exit(f"Missing packages: {', '.join(missing)}\nInstall with: pip install pandas numpy faker pyarrow tqdm")
    if shutil.which("git") is None:
        sys.exit("git is required but was not found on PATH.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=50, help="number of users to generate")
    ap.add_argument("--start", default="2022-07-01", help="window start (use the 1st of a month)")
    ap.add_argument("--end", default="2025-06-30", help="window end (use a month-end date)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data", help="output directory")
    ap.add_argument("--repo-dir", default=None, help="reuse an existing clone instead of cloning")
    ap.add_argument("--keep-raw", action="store_true", help="keep the raw generator output next to --out")
    a = ap.parse_args()

    check_deps()
    import pandas as pd

    w_start, w_end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    if w_start.day != 1:
        sys.exit("--start must be the first day of a month")
    if w_end != w_end + pd.offsets.MonthEnd(0):
        sys.exit("--end must be the last day of a month")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="expense_gen_"))
    try:
        # 1. get the generator
        if a.repo_dir:
            repo = Path(a.repo_dir)
        else:
            repo = tmp / "synthetic-bank-dataset"
            print("Cloning generator...")
            run(["git", "clone", "--quiet", REPO_URL, str(repo)])
            run(["git", "checkout", "--quiet", PINNED_COMMIT], cwd=repo)

        # 2. generate raw data
        raw = tmp / "raw"
        print(f"Generating {a.customers} users, {a.start} to {a.end} ...")
        run([sys.executable, "-m", "bank_gen.main", "--country", "us",
             "--customers", str(a.customers), "--start", a.start, "--end", a.end,
             "--output", str(raw), "--seed", str(a.seed), "--format", "csv"], cwd=repo)

        # 3. reduce to the minimal schema
        t = pd.read_csv(raw / "transactions.csv", parse_dates=["timestamp"])
        c = pd.read_csv(raw / "customers.csv", parse_dates=["customer_since"])

        sub = t["subcategory"].astype(str)
        label = t["label"].astype(str)
        is_loan = sub.isin(["mortgage", "auto_loan", "consumer_loan", "credit_revolving"]) | label.str.startswith("LOAN PMT")
        is_spend = (
            (t["amount"] < 0)
            & ~t["is_transfer"].astype(bool)
            & ~t["category"].eq("income")
            & ~t["transaction_type"].eq("fee")
            & ~is_loan
        )
        t = t[is_spend].copy()

        # first complete month per user: customer_since if it is the 1st, else next month
        since = c["customer_since"].dt.normalize()
        first = since.where(since.dt.day.eq(1), since + pd.offsets.MonthBegin(1))
        first = first.where(first > w_start, w_start)
        start_month = dict(zip(c["customer_id"], first.dt.to_period("M")))

        t["month"] = t["timestamp"].dt.to_period("M")
        t = t[t["month"] >= t["customer_id"].map(start_month)]

        trans = pd.DataFrame({
            "user_id": t["customer_id"],
            "date": t["timestamp"].dt.strftime("%Y-%m-%d"),
            "amount": t["amount"].abs().round(2),
            "note": t["label"],
        }).sort_values(["user_id", "date"], kind="stable")

        users = pd.DataFrame({
            "user_id": list(start_month.keys()),
            "start_month": [str(m) for m in start_month.values()],
        })
        users = users[users["user_id"].isin(trans["user_id"])].sort_values("user_id")

        trans.to_csv(out / "transactions.csv", index=False)
        users.to_csv(out / "users.csv", index=False)

        last = w_end.to_period("M")
        n_months = users["start_month"].map(lambda m: len(pd.period_range(m, last, freq="M")))
        print(f"\nWrote {out / 'transactions.csv'}  ({len(trans):,} rows)")
        print(f"Wrote {out / 'users.csv'}  ({len(users)} users)")
        print(f"Months per user: min {n_months.min()}, median {int(n_months.median())}, max {n_months.max()}; "
              f"users with >= 24 months: {(n_months >= 24).sum()}")

        if a.keep_raw:
            shutil.copytree(raw, out.parent / (out.name + "_raw"), dirs_exist_ok=True)
            print(f"Raw generator output kept in {out.parent / (out.name + '_raw')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()