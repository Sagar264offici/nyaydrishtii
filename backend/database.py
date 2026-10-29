import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from schemas import ReviewStatus

DB_PATH = Path(__file__).parent / "nyaydrishti.db"
CHARGE_SEP = "|"

# All case data below is fictional, for demo/UI purposes only.
SEED_CASES = [
    # case_id, custody_start_date, custody_end_date, charges, review_status, assigned_reviewer, next_follow_up
    ("DEMO-CASE-001", "2026-01-10", None, ["Theft (demo)"], "pending", "Demo Reviewer A", "2026-11-05"),
    ("DEMO-CASE-002", "2025-11-02", None, ["Assault (demo)", "Trespass (demo)"], "in_review", "Demo Reviewer B", "2026-11-10"),
    ("DEMO-CASE-003", "2025-06-15", "2026-02-01", ["Fraud (demo)"], "reviewed", "Demo Reviewer A", None),
    ("DEMO-CASE-004", "2024-09-20", None, ["Robbery (demo)"], "escalated", "Demo Reviewer C", "2026-10-20"),
    ("DEMO-CASE-005", "2026-03-01", None, ["Public Nuisance (demo)"], "pending", "Demo Reviewer B", "2026-12-01"),
    ("DEMO-CASE-006", "2025-12-25", None, ["Theft (demo)", "Forgery (demo)"], "in_review", "Demo Reviewer C", "2026-11-15"),
]


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                custody_start_date TEXT NOT NULL,
                custody_end_date TEXT,
                charges TEXT NOT NULL,
                review_status TEXT NOT NULL,
                assigned_reviewer TEXT NOT NULL,
                next_follow_up TEXT
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (case_id, start, end, CHARGE_SEP.join(charges), status, reviewer, follow_up)
                    for case_id, start, end, charges, status, reviewer, follow_up in SEED_CASES
                ],
            )
        conn.commit()


def _row_to_case(row: sqlite3.Row) -> dict:
    return {
        "case_id": row["case_id"],
        "custody_start_date": row["custody_start_date"],
        "custody_end_date": row["custody_end_date"],
        "charges": row["charges"].split(CHARGE_SEP),
        "review_status": row["review_status"],
        "assigned_reviewer": row["assigned_reviewer"],
        "next_follow_up": row["next_follow_up"],
    }


def list_cases(status: str | None = None, reviewer: str | None = None, q: str | None = None) -> list[dict]:
    query = "SELECT * FROM cases WHERE 1=1"
    params: list[str] = []
    if status:
        query += " AND review_status = ?"
        params.append(status)
    if reviewer:
        query += " AND assigned_reviewer = ?"
        params.append(reviewer)
    if q:
        query += " AND (case_id LIKE ? OR charges LIKE ? OR assigned_reviewer LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY case_id"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_case(r) for r in rows]


def get_case(case_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return _row_to_case(row) if row else None


def compute_metrics() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT review_status, next_follow_up FROM cases").fetchall()
    status_counts = {s.value: 0 for s in ReviewStatus}
    overdue = 0
    today = date.today().isoformat()
    for row in rows:
        status_counts[row["review_status"]] = status_counts.get(row["review_status"], 0) + 1
        if row["next_follow_up"] and row["next_follow_up"] < today:
            overdue += 1
    return {
        "total_cases": len(rows),
        "status_counts": status_counts,
        "overdue_follow_ups": overdue,
    }
