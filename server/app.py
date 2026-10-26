"""SQLite-backed API for the personal-finance mobile app.

Run locally with: ``python server/app.py``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from predictor import predict_next_month  # noqa: E402

DEFAULT_DB_PATH = Path(os.getenv("FINANCE_DB_PATH", Path(__file__).with_name("finance.db")))
PBKDF2_ITERATIONS = 310_000
SESSION_DAYS = 30


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("Enter a valid email address")
        return email


class RegisterRequest(Credentials):
    display_name: str = Field(min_length=1, max_length=80)


class TransactionCreate(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    date: date
    note: str = Field(default="", max_length=250)

    @field_validator("date")
    @classmethod
    def no_future_transactions(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("A transaction date cannot be in the future")
        return value

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str) -> str:
        return value.strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def hash_password(password: str) -> str:
    """Store a salted PBKDF2-HMAC-SHA256 password hash, never plaintext."""
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        ).hex()
        return hmac.compare_digest(actual, expected_hex)
    except (TypeError, ValueError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@contextmanager
def connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database(db_path: Path) -> None:
    with connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL COLLATE NOCASE UNIQUE,
              display_name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              token_hash TEXT NOT NULL UNIQUE,
              expires_at TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              amount REAL NOT NULL CHECK (amount > 0),
              date TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
              ON transactions(user_id, date DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
              ON sessions(token_hash);
            """
        )


def user_payload(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}


def transaction_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "amount": float(row["amount"]), "date": row["date"],
        "note": row["note"], "created_at": row["created_at"],
    }


def month_range(first: date, last: date) -> list[str]:
    cursor = first.replace(day=1)
    end = last.replace(day=1)
    months = []
    while cursor <= end:
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def parse_month(value: str | None) -> str:
    if value is None:
        return date.today().strftime("%Y-%m")
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="month must use YYYY-MM") from exc


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    initialize_database(db_path)
    app = FastAPI(title="Finance API", version="1.0.0")
    app.state.db_path = db_path
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",")],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db(request: Request) -> Iterator[sqlite3.Connection]:
        with connection(request.app.state.db_path) as conn:
            yield conn

    def current_user(
        authorization: Annotated[str | None, Header()] = None,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> sqlite3.Row:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
        token = authorization.removeprefix("Bearer ").strip()
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (hash_token(token), iso_now()),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
        return row

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ping")
    def ping() -> dict:
        """Minimal connectivity check with no authentication requirement."""
        return {"message": "pong"}

    @app.post("/auth/register", status_code=status.HTTP_201_CREATED)
    def register(payload: RegisterRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
        try:
            cursor = conn.execute(
                "INSERT INTO users(email, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (payload.email, payload.display_name.strip(), hash_password(payload.password), iso_now()),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="An account with that email already exists") from exc
        user = conn.execute("SELECT id, email, display_name FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return user_payload(user)

    @app.post("/auth/login")
    def login(payload: Credentials, conn: sqlite3.Connection = Depends(get_db)) -> dict:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        raw_token = secrets.token_urlsafe(32)
        expires = now_utc() + timedelta(days=SESSION_DAYS)
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso_now(),))
        conn.execute(
            "INSERT INTO sessions(user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user["id"], hash_token(raw_token), expires.isoformat(), iso_now()),
        )
        return {"token": raw_token, "expires_at": expires.isoformat(), "user": user_payload(user)}

    @app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        authorization: Annotated[str | None, Header()] = None,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> None:
        if authorization and authorization.startswith("Bearer "):
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(authorization.removeprefix("Bearer ").strip()),))

    @app.get("/me")
    def me(user: sqlite3.Row = Depends(current_user)) -> dict:
        return user_payload(user)

    @app.get("/transactions")
    def list_transactions(
        month: str | None = None,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> list[dict]:
        requested_month = parse_month(month) if month else None
        query = "SELECT * FROM transactions WHERE user_id = ?"
        params: list[object] = [user["id"]]
        if requested_month:
            query += " AND substr(date, 1, 7) = ?"
            params.append(requested_month)
        query += " ORDER BY date DESC, id DESC"
        return [transaction_payload(row) for row in conn.execute(query, params).fetchall()]

    @app.post("/transactions", status_code=status.HTTP_201_CREATED)
    def add_transaction(
        payload: TransactionCreate,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> dict:
        cursor = conn.execute(
            "INSERT INTO transactions(user_id, amount, date, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], round(payload.amount, 2), payload.date.isoformat(), payload.note, iso_now()),
        )
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return transaction_payload(row)

    @app.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_transaction(
        transaction_id: int,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> None:
        cursor = conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user["id"]))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")

    @app.get("/dashboard")
    def dashboard(
        month: str | None = None,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> dict:
        selected = parse_month(month)
        selected_date = datetime.strptime(selected, "%Y-%m").date()
        previous = (selected_date.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        current = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM transactions WHERE user_id = ? AND substr(date, 1, 7) = ?",
            (user["id"], selected),
        ).fetchone()
        prior = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE user_id = ? AND substr(date, 1, 7) = ?",
            (user["id"], previous),
        ).fetchone()
        monthly_rows = conn.execute(
            """SELECT substr(date, 1, 7) AS month, ROUND(SUM(amount), 2) AS total
               FROM transactions WHERE user_id = ? GROUP BY substr(date, 1, 7)
               ORDER BY month DESC LIMIT 6""",
            (user["id"],),
        ).fetchall()
        recent = conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 5", (user["id"],)
        ).fetchall()
        current_total, prior_total = float(current["total"]), float(prior["total"])
        return {
            "month": selected,
            "summary": {
                "total": round(current_total, 2), "transaction_count": current["count"],
                "previous_month_total": round(prior_total, 2),
                "change_percent": round(((current_total - prior_total) / prior_total) * 100, 1) if prior_total else None,
            },
            "monthly_totals": [{"month": row["month"], "total": float(row["total"])} for row in reversed(monthly_rows)],
            "recent_transactions": [transaction_payload(row) for row in recent],
        }

    @app.get("/prediction")
    def prediction(
        user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)
    ) -> dict:
        # Only full months are passed to the model; the in-progress current month is excluded.
        current_month = date.today().replace(day=1)
        last_completed = current_month - timedelta(days=1)
        first = conn.execute("SELECT MIN(date) AS first_date FROM transactions WHERE user_id = ?", (user["id"],)).fetchone()["first_date"]
        if first is None or date.fromisoformat(first).replace(day=1) > last_completed.replace(day=1):
            return {"forecast": 0.0, "next_month": current_month.strftime("%Y-%m"), "history_months": 0, "method": "insufficient_history"}
        totals = {
            row["month"]: float(row["total"])
            for row in conn.execute(
                """SELECT substr(date, 1, 7) AS month, SUM(amount) AS total FROM transactions
                   WHERE user_id = ? AND date < ? GROUP BY substr(date, 1, 7)""",
                (user["id"], current_month.isoformat()),
            ).fetchall()
        }
        months = month_range(date.fromisoformat(first), last_completed)
        history = [totals.get(month, 0.0) for month in months]
        next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        if len(history) < 3:
            method = "insufficient_history_mean"
        else:
            # The saved policy is read by predictor.py; it currently selects MA3 in all tiers.
            method = "saved_tier_policy"
        return {
            "forecast": round(predict_next_month(history, next_month.month), 2),
            "next_month": next_month.strftime("%Y-%m"), "history_months": len(history), "method": method,
        }

    return app


app = create_app()


if __name__ == "__main__":
    # Normal local start command: `python server/app.py`.
    # Uvicorn is the ASGI server FastAPI requires internally; callers do not
    # need to invoke its CLI directly.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=42069)
