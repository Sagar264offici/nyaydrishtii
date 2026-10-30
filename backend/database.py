import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from schemas import FactType, FollowUpStatus, ReviewStatus, VerificationStatus

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                value_json TEXT,
                original_value_json TEXT,
                source_filename TEXT,
                source_page INTEGER,
                extraction_method TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                verification_note TEXT,
                UNIQUE(case_id, fact_type)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                outcome TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS follow_ups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                assigned_reviewer TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                completed_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                entity_id TEXT,
                actor TEXT,
                description TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL
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
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        case_rows = conn.execute("SELECT review_status FROM cases").fetchall()
        followup_rows = conn.execute("SELECT status, due_at FROM follow_ups").fetchall()

    status_counts = {s.value: 0 for s in ReviewStatus}
    for row in case_rows:
        status_counts[row["review_status"]] = status_counts.get(row["review_status"], 0) + 1

    # overdue_follow_ups reflects the persisted follow_ups table (real tasks with a
    # status lifecycle), not the legacy Case.next_follow_up column (a single static
    # seed-data date with no task lifecycle behind it).
    follow_up_status_counts = {s.value: 0 for s in FollowUpStatus}
    overdue = 0
    for row in followup_rows:
        follow_up_status_counts[row["status"]] = follow_up_status_counts.get(row["status"], 0) + 1
        if row["due_at"] < now_iso and row["status"] not in (
            FollowUpStatus.completed.value,
            FollowUpStatus.cancelled.value,
        ):
            overdue += 1

    return {
        "total_cases": len(case_rows),
        "status_counts": status_counts,
        "overdue_follow_ups": overdue,
        "follow_up_status_counts": follow_up_status_counts,
    }


# --- Facts (extracted from uploaded documents, pending reviewer verification) ---

# Columns update_fact() is allowed to write — never accepts arbitrary caller-supplied
# column names, since those are built into an f-string below.
_UPDATABLE_FACT_COLUMNS = {
    "value": "value_json",
    "verification_status": "verification_status",
    "reviewed_by": "reviewed_by",
    "reviewed_at": "reviewed_at",
    "verification_note": "verification_note",
}


def _row_to_fact(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "fact_type": row["fact_type"],
        "value": json.loads(row["value_json"]) if row["value_json"] is not None else None,
        "original_value": (
            json.loads(row["original_value_json"]) if row["original_value_json"] is not None else None
        ),
        "source_filename": row["source_filename"],
        "source_page": row["source_page"],
        "extraction_method": row["extraction_method"],
        "verification_status": row["verification_status"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": row["reviewed_at"],
        "verification_note": row["verification_note"],
    }


def list_facts(case_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM facts WHERE case_id = ? ORDER BY fact_type", (case_id,)
        ).fetchall()
    return [_row_to_fact(r) for r in rows]


def get_fact(case_id: str, fact_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM facts WHERE case_id = ? AND id = ?", (case_id, fact_id)
        ).fetchone()
    return _row_to_fact(row) if row else None


def upsert_extracted_facts(
    case_id: str, filename: str, extraction_method: str, candidates: dict
) -> None:
    """Merge one document upload's candidate facts into the facts table.

    Every FactType gets a row after this call. A fact a human already verified
    or flagged as conflicting is never touched — a later upload must not
    silently overwrite or revert a reviewer's judgement.
    """
    with get_connection() as conn:
        for fact_type in FactType:
            cand = candidates.get(fact_type) or candidates.get(fact_type.value)
            existing = conn.execute(
                "SELECT * FROM facts WHERE case_id = ? AND fact_type = ?",
                (case_id, fact_type.value),
            ).fetchone()

            if existing is None:
                if cand is not None:
                    value_json = json.dumps(cand.get("value"))
                    conn.execute(
                        """INSERT INTO facts
                           (case_id, fact_type, value_json, original_value_json,
                            source_filename, source_page, extraction_method, verification_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            case_id,
                            fact_type.value,
                            value_json,
                            value_json,
                            filename,
                            cand.get("page"),
                            extraction_method,
                            VerificationStatus.unverified.value,
                        ),
                    )
                else:
                    conn.execute(
                        """INSERT INTO facts
                           (case_id, fact_type, value_json, original_value_json,
                            source_filename, source_page, extraction_method, verification_status)
                           VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?)""",
                        (case_id, fact_type.value, extraction_method, VerificationStatus.unknown.value),
                    )
                continue

            if existing["verification_status"] in (
                VerificationStatus.verified.value,
                VerificationStatus.conflict.value,
            ):
                continue  # human-reviewed already — leave exactly as-is

            if cand is not None:
                original = existing["original_value_json"]
                if original is None:
                    original = json.dumps(cand.get("value"))
                conn.execute(
                    """UPDATE facts SET value_json = ?, original_value_json = ?,
                           source_filename = ?, source_page = ?, extraction_method = ?,
                           verification_status = ?
                       WHERE id = ?""",
                    (
                        json.dumps(cand.get("value")),
                        original,
                        filename,
                        cand.get("page"),
                        extraction_method,
                        VerificationStatus.unverified.value,
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """UPDATE facts SET value_json = NULL,
                           source_filename = NULL, source_page = NULL, extraction_method = ?,
                           verification_status = ?
                       WHERE id = ?""",
                    (extraction_method, VerificationStatus.unknown.value, existing["id"]),
                )
        conn.commit()


def update_fact(case_id: str, fact_id: int, audit: dict | None = None, **changes) -> dict | None:
    """Apply a reviewer's edit to one fact. `changes` keys must be in
    _UPDATABLE_FACT_COLUMNS (value, verification_status, reviewed_by,
    reviewed_at, verification_note); original_value is never touched here.

    If `audit` is given, its audit_log row is inserted in the SAME
    transaction as the fact update -- both succeed or neither does."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM facts WHERE case_id = ? AND id = ?", (case_id, fact_id)
        ).fetchone()
        if existing is None:
            return None

        set_clauses = []
        params: list = []
        for key, value in changes.items():
            column = _UPDATABLE_FACT_COLUMNS[key]
            set_clauses.append(f"{column} = ?")
            params.append(json.dumps(value) if key == "value" else value)

        if set_clauses:
            params.extend([case_id, fact_id])
            conn.execute(
                f"UPDATE facts SET {', '.join(set_clauses)} WHERE case_id = ? AND id = ?",
                params,
            )
        if audit is not None:
            _insert_audit_event(conn, created_at=datetime.now(timezone.utc).isoformat(), **audit)
        conn.commit()

        row = conn.execute(
            "SELECT * FROM facts WHERE case_id = ? AND id = ?", (case_id, fact_id)
        ).fetchone()
    return _row_to_fact(row)


# --- Section 479 rule-engine evaluations ---
#
# Append-only: there is deliberately no update/delete function for this table.
# Re-evaluating a case always INSERTs a new row; history is never overwritten.


def _row_to_evaluation(row: sqlite3.Row) -> dict:
    result = json.loads(row["result_json"])
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "created_at": row["created_at"],
        "reviewer": row["reviewer"],
        "rule_version": row["rule_version"],
        "outcome": row["outcome"],
        **result,
    }


def insert_evaluation(
    case_id: str, reviewer: str, rule_version: str, outcome: str, result: dict, audit: dict | None = None
) -> dict:
    """Append-only: there is deliberately no update/delete function for this
    table. If `audit` is given, its audit_log row (entity_id filled in with
    this new evaluation's id) is inserted in the SAME transaction."""
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO evaluations
               (case_id, created_at, reviewer, rule_version, outcome, result_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (case_id, created_at, reviewer, rule_version, outcome, json.dumps(result)),
        )
        new_id = cursor.lastrowid
        if audit is not None:
            _insert_audit_event(conn, created_at=created_at, **{**audit, "entity_id": str(new_id)})
        conn.commit()
        row = conn.execute("SELECT * FROM evaluations WHERE id = ?", (new_id,)).fetchone()
    return _row_to_evaluation(row)


def list_evaluations(case_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM evaluations WHERE case_id = ? ORDER BY created_at DESC, id DESC", (case_id,)
        ).fetchall()
    return [_row_to_evaluation(r) for r in rows]


# --- Follow-up tasks ---

_UPDATABLE_FOLLOWUP_COLUMNS = {
    "title": "title",
    "description": "description",
    "assigned_reviewer": "assigned_reviewer",
    "due_at": "due_at",
    "status": "status",
    "updated_at": "updated_at",
    "completed_at": "completed_at",
    "completed_by": "completed_by",
}


def _row_to_follow_up(row: sqlite3.Row, now_iso: str) -> dict:
    is_overdue = row["due_at"] < now_iso and row["status"] not in (
        FollowUpStatus.completed.value,
        FollowUpStatus.cancelled.value,
    )
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "title": row["title"],
        "description": row["description"],
        "assigned_reviewer": row["assigned_reviewer"],
        "due_at": row["due_at"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "completed_by": row["completed_by"],
        "is_overdue": is_overdue,
    }


def create_follow_up(
    case_id: str, title: str, description: str | None, assigned_reviewer: str, due_at: str, audit: dict
) -> dict:
    """Insert a follow-up and its creation audit event in one transaction."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO follow_ups
               (case_id, title, description, assigned_reviewer, due_at, status,
                created_at, updated_at, completed_at, completed_by)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)""",
            (case_id, title, description, assigned_reviewer, due_at, now, now),
        )
        new_id = cursor.lastrowid
        _insert_audit_event(conn, created_at=now, **{**audit, "entity_id": str(new_id)})
        conn.commit()
        row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (new_id,)).fetchone()
    return _row_to_follow_up(row, now)


def list_follow_ups(
    status: str | None = None,
    reviewer: str | None = None,
    case_id: str | None = None,
    overdue: bool | None = None,
) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    query = "SELECT * FROM follow_ups WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if reviewer:
        query += " AND assigned_reviewer = ?"
        params.append(reviewer)
    if case_id:
        query += " AND case_id = ?"
        params.append(case_id)
    if overdue is not None:
        clause = "(due_at < ? AND status NOT IN (?, ?))"
        query += f" AND {clause}" if overdue else f" AND NOT {clause}"
        params.extend([now_iso, FollowUpStatus.completed.value, FollowUpStatus.cancelled.value])
    query += " ORDER BY due_at ASC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_follow_up(r, now_iso) for r in rows]


def get_follow_up(followup_id: int) -> dict | None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (followup_id,)).fetchone()
    return _row_to_follow_up(row, now_iso) if row else None


def update_follow_up(followup_id: int, changes: dict, audit: dict | None) -> dict | None:
    """Apply an edit/status-transition to one follow-up. `changes` keys must be
    in _UPDATABLE_FOLLOWUP_COLUMNS. If `audit` is given, its audit_log row is
    inserted in the SAME transaction as the follow-up update."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (followup_id,)).fetchone()
        if existing is None:
            return None

        set_clauses = []
        params: list = []
        for key, value in changes.items():
            column = _UPDATABLE_FOLLOWUP_COLUMNS[key]
            set_clauses.append(f"{column} = ?")
            params.append(value)

        if set_clauses:
            params.append(followup_id)
            conn.execute(f"UPDATE follow_ups SET {', '.join(set_clauses)} WHERE id = ?", params)
        if audit is not None:
            _insert_audit_event(conn, created_at=now_iso, **audit)
        conn.commit()

        row = conn.execute("SELECT * FROM follow_ups WHERE id = ?", (followup_id,)).fetchone()
    return _row_to_follow_up(row, now_iso)


def update_case_status(case_id: str, review_status: str, audit: dict) -> dict | None:
    """Change a case's review_status and log the audit event in one transaction."""
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if existing is None:
            return None
        conn.execute("UPDATE cases SET review_status = ? WHERE case_id = ?", (review_status, case_id))
        _insert_audit_event(conn, created_at=datetime.now(timezone.utc).isoformat(), **audit)
        conn.commit()
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return _row_to_case(row)


# --- Audit trail ---
#
# Append-only: there is deliberately no update/delete function for this log.
# Every write above that logs an event does so in the same transaction as the
# change it describes (see update_fact/insert_evaluation/create_follow_up/
# update_follow_up/update_case_status), so a logged event and the change it
# describes always succeed or fail together.


def _insert_audit_event(
    conn: sqlite3.Connection,
    *,
    created_at: str,
    case_id: str,
    event_type: str,
    entity_id: str | None,
    actor: str | None,
    description: str,
    before: dict | None,
    after: dict | None,
) -> None:
    conn.execute(
        """INSERT INTO audit_log
           (case_id, event_type, entity_id, actor, description, before_json, after_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            event_type,
            entity_id,
            actor,
            description,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            created_at,
        ),
    )


def _row_to_audit_event(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "event_type": row["event_type"],
        "entity_id": row["entity_id"],
        "actor": row["actor"],
        "description": row["description"],
        "before": json.loads(row["before_json"]) if row["before_json"] is not None else None,
        "after": json.loads(row["after_json"]) if row["after_json"] is not None else None,
        "created_at": row["created_at"],
    }


def list_audit_events(case_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE case_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (case_id, limit, offset),
        ).fetchall()
    return [_row_to_audit_event(r) for r in rows]
