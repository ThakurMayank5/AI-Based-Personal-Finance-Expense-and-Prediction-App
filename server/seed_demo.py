"""Create/reset a safe demo account with realistic sample expenses.

Run from the repository root:
    python -m server.seed_demo

This resets only the demo account named by DEMO_EMAIL. It never modifies any
other user's data.
"""
from __future__ import annotations

from datetime import date

from server.app import DEFAULT_DB_PATH, connection, hash_password, initialize_database, iso_now

DEMO_EMAIL = "demo@financetrack.local"
DEMO_PASSWORD = "FinanceDemo123!"
DEMO_NAME = "Demo User"


def add_months(month: date, delta: int) -> date:
    index = month.year * 12 + (month.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def main() -> None:
    initialize_database(DEFAULT_DB_PATH)
    current_month = date.today().replace(day=1)
    # Six completed monthly histories, newest last, plus this month's activity.
    completed = [
        [(4200, "Rent contribution", 2), (2850, "Groceries", 11), (1640, "Metro and rides", 21)],
        [(4200, "Rent contribution", 2), (3190, "Groceries", 12), (1290, "Dining out", 24)],
        [(4200, "Rent contribution", 2), (2475, "Groceries", 11), (1860, "Utilities", 20)],
        [(4200, "Rent contribution", 2), (3520, "Groceries", 12), (2400, "Weekend trip", 22)],
        [(4200, "Rent contribution", 2), (3010, "Groceries", 10), (2160, "Internet and phone", 20)],
        [(4200, "Rent contribution", 2), (3340, "Groceries", 12), (1940, "Health and fitness", 21)],
    ]
    current = [(4200, "Rent contribution", 2), (1860, "Groceries", 9), (720, "Coffee and snacks", 18)]

    with connection(DEFAULT_DB_PATH) as conn:
        # Reset only this known demonstration identity, making reruns predictable.
        conn.execute("DELETE FROM users WHERE email = ?", (DEMO_EMAIL,))
        cursor = conn.execute(
            "INSERT INTO users(email, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (DEMO_EMAIL, DEMO_NAME, hash_password(DEMO_PASSWORD), iso_now()),
        )
        user_id = cursor.lastrowid
        created_at = iso_now()
        for index, transactions in enumerate(completed):
            month = add_months(current_month, index - len(completed))
            for amount, note, day in transactions:
                conn.execute(
                    "INSERT INTO transactions(user_id, amount, date, note, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, amount, month.replace(day=day).isoformat(), note, created_at),
                )
        for amount, note, day in current:
            conn.execute(
                "INSERT INTO transactions(user_id, amount, date, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, current_month.replace(day=day).isoformat(), note, created_at),
            )
    print(f"Demo account created in {DEFAULT_DB_PATH}")
    print(f"Email: {DEMO_EMAIL}")
    print(f"Password: {DEMO_PASSWORD}")
    print(f"Seeded {len(completed) * 3 + len(current)} expenses across seven months.")


if __name__ == "__main__":
    main()
