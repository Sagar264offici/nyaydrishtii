from datetime import date, datetime, timedelta, timezone

import pymupdf
import pytest
from fastapi.testclient import TestClient

import database
from main import app


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    """Every test runs against its own throw-away sqlite file under pytest's
    per-test tmp_path, never the real backend/nyaydrishti.db a developer might
    be running the app against locally. database.get_connection() reads the
    module-level DB_PATH global at call time, so monkeypatching the attribute
    here redirects every db call made during the test -- no production code
    needs to change. Each test also gets a freshly re-seeded database this
    way, since a shared file would otherwise persist facts/evaluations across
    test functions within one pytest run."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_nyaydrishti.db")
    yield


def test_health():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_list_cases_returns_seeded_data():
    with TestClient(app) as client:
        resp = client.get("/api/cases")
        assert resp.status_code == 200
        cases = resp.json()
        assert len(cases) >= 6
        assert "DEMO-CASE-001" in {c["case_id"] for c in cases}


def test_filter_by_status():
    with TestClient(app) as client:
        resp = client.get("/api/cases", params={"status": "pending"})
        assert resp.status_code == 200
        cases = resp.json()
        assert len(cases) > 0
        assert all(c["review_status"] == "pending" for c in cases)


def test_search_query_matches_charges():
    with TestClient(app) as client:
        resp = client.get("/api/cases", params={"q": "Forgery"})
        assert resp.status_code == 200
        cases = resp.json()
        assert any("DEMO-CASE-006" == c["case_id"] for c in cases)


def test_invalid_status_returns_422():
    with TestClient(app) as client:
        resp = client.get("/api/cases", params={"status": "not-a-real-status"})
        assert resp.status_code == 422


def test_case_detail_found():
    with TestClient(app) as client:
        resp = client.get("/api/cases/DEMO-CASE-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["case_id"] == "DEMO-CASE-001"
        assert isinstance(body["charges"], list)


def test_case_detail_not_found():
    with TestClient(app) as client:
        resp = client.get("/api/cases/NOT-A-REAL-CASE")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


def test_metrics_counts_match_cases():
    with TestClient(app) as client:
        cases = client.get("/api/cases").json()
        metrics = client.get("/api/metrics").json()

        assert metrics["total_cases"] == len(cases)
        assert sum(metrics["status_counts"].values()) == metrics["total_cases"]

        # overdue_follow_ups now reflects the persisted follow_ups table, not the
        # legacy Case.next_follow_up seed column -- on a fresh DB with no
        # follow-ups created yet, it must be 0, not derived from seed dates.
        assert metrics["overdue_follow_ups"] == 0
        assert metrics["follow_up_status_counts"] == {
            "pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0,
        }

        past_due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future_due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-001", "title": "Overdue one", "assigned_reviewer": "R", "due_at": past_due},
        )
        client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-002", "title": "Not due yet", "assigned_reviewer": "R", "due_at": future_due},
        )
        completed = client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-003", "title": "Overdue but done", "assigned_reviewer": "R", "due_at": past_due},
        ).json()
        client.patch(
            f"/api/followups/{completed['id']}", json={"status": "completed", "reviewer": "R"}
        )

        metrics2 = client.get("/api/metrics").json()
        # Only the first follow-up is both overdue AND not completed/cancelled.
        assert metrics2["overdue_follow_ups"] == 1
        assert metrics2["follow_up_status_counts"] == {
            "pending": 2, "in_progress": 0, "completed": 1, "cancelled": 0,
        }


# --- Document upload / fact extraction & verification ---


def _make_pdf(pages_lines: list[list[str]]) -> bytes:
    """Build a synthetic in-memory PDF with the given per-page lines of text."""
    doc = pymupdf.open()
    for lines in pages_lines:
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line)
            y += 20
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_preview_valid_text_pdf_extracts_facts_with_pages():
    pdf_bytes = _make_pdf(
        [
            [
                "Case Record",
                "Custody start date: 10 January 2026",
                "Current charges: Theft, Criminal Trespass",
            ],
            [
                "Maximum punishment: 7 years imprisonment",
                "Section 379 IPC provides for: imprisonment up to 7 years",
                "The accused is a first-time offender and senior citizen",
            ],
        ]
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-002"},
            files={"file": ("record.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["extraction_method"] == "text"
        assert body["page_count"] == 2
        assert body["message"] is None

        facts = {f["fact_type"]: f for f in body["facts"]}
        assert len(facts) == 10  # every FactType always comes back, found or not

        start = facts["custody_start_date"]
        assert start["value"] == "2026-01-10"
        assert start["original_value"] == "2026-01-10"
        assert start["source_page"] == 1
        assert start["extraction_method"] == "text"
        assert start["verification_status"] == "unverified"

        charges = facts["current_charges"]
        assert charges["value"] == ["Theft", "Criminal Trespass"]
        assert charges["source_page"] == 1

        punishment = facts["max_punishment"]
        assert punishment["value"] == "7 years imprisonment"
        assert punishment["source_page"] == 2

        assert facts["max_punishment_source"]["value"] == "imprisonment up to 7 years"
        assert set(facts["exception_flags"]["value"]) == {"first-time offender", "senior citizen"}

        # not mentioned in the document at all -> unknown, never invented
        assert facts["custody_end_date"]["value"] is None
        assert facts["custody_end_date"]["verification_status"] == "unknown"
        assert facts["other_pending_cases"]["value"] is None
        assert facts["other_pending_cases"]["verification_status"] == "unknown"

        # a fact extracted from a document is never auto-verified
        assert all(f["verification_status"] in ("unverified", "unknown") for f in facts.values())


def test_preview_rejects_non_pdf_file():
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("notes.txt", b"just some plain text", "text/plain")},
        )
        assert resp.status_code == 400
        assert "pdf" in resp.json()["detail"].lower()


def test_preview_rejects_corrupted_pdf():
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("broken.pdf", b"%PDF-1.4 truncated, not a real pdf body", "application/pdf")},
        )
        assert resp.status_code == 422
        assert "could not read" in resp.json()["detail"].lower()


def test_preview_scanned_pdf_with_ocr_unavailable(monkeypatch):
    # Force the "OCR unavailable" branch deterministically, regardless of
    # whether this host machine has tesseract installed.
    monkeypatch.setattr("main.ocr_available", lambda: False)
    pdf_bytes = _make_pdf([[]])  # one page, no text at all (simulates a scan)

    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-003"},
            files={"file": ("scanned.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["extraction_method"] == "unavailable"
        assert body["message"] and "manually" in body["message"].lower()
        assert all(f["verification_status"] == "unknown" for f in body["facts"])
        assert all(f["value"] is None for f in body["facts"])


def test_patch_fact_reviewer_edit_and_verify_preserves_original():
    pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-004"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "custody_start_date")
        original_value = fact["original_value"]
        assert original_value == "2026-01-10"

        patched = client.patch(
            f"/api/cases/DEMO-CASE-004/facts/{fact['id']}",
            json={"value": "2026-01-12", "verification_status": "verified", "reviewer": "Reviewer Q"},
        )
        assert patched.status_code == 200
        updated = patched.json()
        assert updated["value"] == "2026-01-12"
        assert updated["verification_status"] == "verified"
        assert updated["reviewed_by"] == "Reviewer Q"
        assert updated["reviewed_at"] is not None
        assert updated["original_value"] == original_value  # unchanged by the edit


def test_patch_fact_conflict_requires_reviewer():
    pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-005"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "custody_start_date")

        rejected = client.patch(
            f"/api/cases/DEMO-CASE-005/facts/{fact['id']}",
            json={"verification_status": "conflict"},
        )
        assert rejected.status_code == 422

        flagged = client.patch(
            f"/api/cases/DEMO-CASE-005/facts/{fact['id']}",
            json={"verification_status": "conflict", "reviewer": "Reviewer R"},
        )
        assert flagged.status_code == 200
        assert flagged.json()["verification_status"] == "conflict"
        assert flagged.json()["reviewed_by"] == "Reviewer R"


def test_patch_fact_explicit_null_verification_status_is_a_no_op():
    # PATCH body can distinguish "field omitted" from "field explicitly null";
    # an explicit null for verification_status must not crash the endpoint.
    pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "custody_start_date")

        patched = client.patch(
            f"/api/cases/DEMO-CASE-001/facts/{fact['id']}",
            json={"verification_status": None},
        )
        assert patched.status_code == 200
        assert patched.json()["verification_status"] == "unverified"  # unchanged


def test_facts_endpoint_regression():
    with TestClient(app) as client:
        # no document ever uploaded for this case -> empty, no placeholder rows
        resp = client.get("/api/cases/DEMO-CASE-006/facts")
        assert resp.status_code == 200
        assert resp.json() == []

        missing = client.get("/api/cases/NOT-A-REAL-CASE/facts")
        assert missing.status_code == 404


def test_patch_fact_value_on_unknown_fact_becomes_unverified_not_verified():
    # Entering a value for a fact that was "unknown" must not silently stay
    # "unknown" (misleading) or jump to "verified" (auto-verifying is unsafe).
    pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])  # no charges mentioned
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-006"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        charges_fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "current_charges")
        assert charges_fact["verification_status"] == "unknown"

        patched = client.patch(
            f"/api/cases/DEMO-CASE-006/facts/{charges_fact['id']}",
            json={"value": ["Manually entered charge"]},
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["value"] == ["Manually entered charge"]
        assert body["verification_status"] == "unverified"
        assert body["reviewed_by"] is None  # editing alone doesn't verify


def test_preview_missing_case_404():
    pdf_bytes = _make_pdf([["hello"]])
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "NOT-A-REAL-CASE"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 404


# --- Section 479 BNSS rule-engine evaluations ---


def _upload_blank_pdf(client, case_id: str) -> dict:
    """Upload a document with no recognizable keywords, just to materialize a
    full set of (mostly 'unknown') fact rows for the case."""
    pdf_bytes = _make_pdf([["no matching keywords in this line at all"]])
    resp = client.post(
        "/api/documents/preview",
        data={"case_id": case_id},
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    return {f["fact_type"]: f["id"] for f in resp.json()["facts"]}


def _verify(client, case_id: str, fact_ids: dict, fact_type: str, value, reviewer="Rule Test Reviewer"):
    resp = client.patch(
        f"/api/cases/{case_id}/facts/{fact_ids[fact_type]}",
        json={"value": value, "verification_status": "verified", "reviewer": reviewer},
    )
    assert resp.status_code == 200, resp.json()
    return resp.json()


def _setup_critical_facts(
    client,
    case_id: str,
    *,
    custody_start_date: str,
    max_punishment_years: float = 10.0,
    death_or_life_punishment: bool = False,
    exception_flags: list[str] | None = None,
    other_pending_cases: list[str] | None = None,
    custody_end_date: str | None = None,
    accused_caused_delay_days: int | None = None,
) -> dict:
    fact_ids = _upload_blank_pdf(client, case_id)
    _verify(client, case_id, fact_ids, "custody_start_date", custody_start_date)
    _verify(client, case_id, fact_ids, "max_punishment_years", max_punishment_years)
    _verify(client, case_id, fact_ids, "death_or_life_punishment", death_or_life_punishment)
    _verify(client, case_id, fact_ids, "exception_flags", exception_flags or [])
    _verify(client, case_id, fact_ids, "other_pending_cases", other_pending_cases or [])
    if custody_end_date is not None:
        _verify(client, case_id, fact_ids, "custody_end_date", custody_end_date)
    if accused_caused_delay_days is not None:
        _verify(client, case_id, fact_ids, "accused_caused_delay_days", accused_caused_delay_days)
    return fact_ids


def _run_evaluation(client, case_id: str, reviewer="Rule Test Reviewer"):
    resp = client.post(f"/api/cases/{case_id}/evaluations", json={"reviewer": reviewer})
    assert resp.status_code == 200, resp.json()
    return resp.json()


def test_evaluation_one_half_threshold_reached():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        # max 8y -> half threshold = round(8 * 365.25 / 2) = 1461 days, exactly at the boundary.
        start = (date.today() - timedelta(days=1461)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=8.0)
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "REVIEW_THRESHOLD_REACHED"
        assert result["calculation"]["custody_days_effective"] == result["calculation"]["half_threshold_days"] == 1461
        assert result["rule_version"] == "bnss-479-v1"
        assert any(t["rule"] == "one_half_threshold" for t in result["trace"])


def test_evaluation_one_third_threshold_first_time_offender_reached():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        # max 9y -> third threshold = round(9 * 365.25 / 3) = 1096 days.
        start = (date.today() - timedelta(days=1096)).isoformat()
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=9.0,
            exception_flags=["first-time offender"],
        )
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "REVIEW_THRESHOLD_REACHED"
        assert result["calculation"]["custody_days_effective"] < result["calculation"]["half_threshold_days"]
        assert result["calculation"]["custody_days_effective"] >= result["calculation"]["third_threshold_days"]
        assert result["inputs"]["first_time_offender"] is True


def test_evaluation_one_third_reached_but_not_first_time_offender_not_reached():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-003"
        start = (date.today() - timedelta(days=1096)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=9.0, exception_flags=[])
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "THRESHOLD_NOT_REACHED"
        assert result["inputs"]["first_time_offender"] is False


def test_evaluation_threshold_not_reached_short_custody():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-004"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "THRESHOLD_NOT_REACHED"


def test_evaluation_boundary_leap_year_and_outer_cap():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-005"
        # 2024 is a leap year: 2024-01-01 -> 2025-01-01 spans 366 real calendar days,
        # not the naive 365. max 1y -> outer cap = round(365.25) = 365 days, so this
        # also trips the absolute third-proviso cap.
        _setup_critical_facts(
            client, case_id,
            custody_start_date="2024-01-01", custody_end_date="2025-01-01",
            max_punishment_years=1.0,
        )
        result = _run_evaluation(client, case_id)
        assert result["calculation"]["custody_days_raw"] == 366
        assert result["calculation"]["custody_days_effective"] == 366
        assert result["outcome"] == "REVIEW_THRESHOLD_REACHED"
        assert any(t["rule"] == "outer_cap_third_proviso" and t["result"] == "fail" for t in result["trace"])


def test_evaluation_blocked_when_facts_never_uploaded_or_verified():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-006"
        _upload_blank_pdf(client, case_id)  # creates rows, all still "unknown"
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "BLOCKED_MISSING_FACTS"
        assert len(result["blockers"]) == 5
        assert all("missing" in b for b in result["blockers"])


def test_evaluation_blocked_when_extracted_but_unverified():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        pdf_bytes = _make_pdf([["Custody start date: 10 January 2026", "Maximum punishment: 7 years imprisonment"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        facts = {f["fact_type"]: f for f in resp.json()["facts"]}
        assert facts["custody_start_date"]["verification_status"] == "unverified"
        assert facts["max_punishment_years"]["verification_status"] == "unverified"

        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "BLOCKED_MISSING_FACTS"
        assert any("custody_start_date" in b and "unverified" in b for b in result["blockers"])


def test_evaluation_blocked_when_critical_fact_conflicting():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        start = (date.today() - timedelta(days=10)).isoformat()
        fact_ids = _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        flagged = client.patch(
            f"/api/cases/{case_id}/facts/{fact_ids['exception_flags']}",
            json={"verification_status": "conflict", "reviewer": "Reviewer Z"},
        )
        assert flagged.status_code == 200

        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "BLOCKED_MISSING_FACTS"
        assert any("exception_flags" in b and "conflict" in b for b in result["blockers"])


def test_evaluation_death_or_life_punishment_escalates():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-003"
        start = (date.today() - timedelta(days=2000)).isoformat()
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=5.0, death_or_life_punishment=True,
        )
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "ESCALATED_LEGAL_REVIEW"
        assert any("death or life" in r for r in result["escalation_reasons"])


def test_evaluation_multiple_pending_cases_escalates():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-004"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=10.0,
            other_pending_cases=["FIR 99/2025 at Demo PS"],
        )
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "ESCALATED_LEGAL_REVIEW"
        assert any("other pending" in r for r in result["escalation_reasons"])


def test_evaluation_outer_cap_overrides_multiple_pending_cases_bar():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-005"
        # max 1y -> outer cap ~365 days; 400 days of custody exceeds it even though
        # other pending cases are on record (third proviso overrides sub-section (2)).
        start = (date.today() - timedelta(days=400)).isoformat()
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=1.0,
            other_pending_cases=["FIR 12/2024 at Demo PS"],
        )
        result = _run_evaluation(client, case_id)
        assert result["outcome"] == "REVIEW_THRESHOLD_REACHED"
        assert any(t["rule"] == "outer_cap_third_proviso" for t in result["trace"])


def test_evaluation_accused_caused_delay_excluded_from_custody_count():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-006"
        start = (date.today() - timedelta(days=370)).isoformat()
        # max 2y -> half threshold ~365 days. Raw custody (370d) alone would clear it;
        # excluding 10 accused-caused delay days (360d) must not.
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=2.0,
            accused_caused_delay_days=10,
        )
        result = _run_evaluation(client, case_id)
        calc = result["calculation"]
        assert calc["custody_days_raw"] == 370
        assert calc["accused_caused_delay_days_excluded"] == 10
        assert calc["custody_days_effective"] == 360
        assert calc["custody_days_raw"] >= calc["half_threshold_days"]
        assert calc["custody_days_effective"] < calc["half_threshold_days"]
        assert result["outcome"] == "THRESHOLD_NOT_REACHED"


def test_evaluation_history_preserved_across_reevaluation():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        start = (date.today() - timedelta(days=10)).isoformat()
        fact_ids = _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)

        first = _run_evaluation(client, case_id, reviewer="Reviewer One")
        assert first["outcome"] == "THRESHOLD_NOT_REACHED"
        assert first["facts_snapshot"] and len(first["facts_snapshot"]) == 10

        # Move custody_start_date far enough back that the second run reaches threshold.
        new_start = (date.today() - timedelta(days=4000)).isoformat()
        _verify(client, case_id, fact_ids, "custody_start_date", new_start, reviewer="Reviewer Two")
        second = _run_evaluation(client, case_id, reviewer="Reviewer Two")
        assert second["outcome"] == "REVIEW_THRESHOLD_REACHED"

        history = client.get(f"/api/cases/{case_id}/evaluations")
        assert history.status_code == 200
        records = history.json()
        assert len(records) == 2  # both runs kept -- re-evaluation never overwrites
        assert {r["id"] for r in records} == {first["id"], second["id"]}
        assert records[0]["id"] == second["id"]  # newest first
        assert records[0]["outcome"] == "REVIEW_THRESHOLD_REACHED"
        assert records[1]["outcome"] == "THRESHOLD_NOT_REACHED"
        assert all(r["rule_version"] == "bnss-479-v1" for r in records)


def test_evaluation_requires_reviewer():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        resp = client.post(f"/api/cases/{case_id}/evaluations", json={"reviewer": "   "})
        assert resp.status_code == 422


def test_evaluation_missing_case_404():
    with TestClient(app) as client:
        assert client.post("/api/cases/NOT-A-REAL-CASE/evaluations", json={"reviewer": "X"}).status_code == 404
        assert client.get("/api/cases/NOT-A-REAL-CASE/evaluations").status_code == 404


def test_evaluations_endpoint_empty_before_any_run():
    with TestClient(app) as client:
        resp = client.get("/api/cases/DEMO-CASE-003/evaluations")
        assert resp.status_code == 200
        assert resp.json() == []


# --- Counsel Review Pack PDF ---


def _pdf_text(content: bytes) -> str:
    doc = pymupdf.open(stream=content, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_review_pack_with_evaluation_includes_outcome_and_trace():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        start = (date.today() - timedelta(days=5000)).isoformat()
        _setup_critical_facts(
            client, case_id, custody_start_date=start, max_punishment_years=8.0,
            exception_flags=["first-time offender"],
        )
        eval_result = _run_evaluation(client, case_id, reviewer="Counsel Reviewer")
        assert eval_result["outcome"] == "REVIEW_THRESHOLD_REACHED"

        resp = client.get(f"/api/cases/{case_id}/review-pack")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert case_id in resp.headers["content-disposition"]
        assert resp.content.startswith(b"%PDF")

        text = _pdf_text(resp.content)
        assert "Counsel Review Pack" in text
        assert case_id in text
        assert "REVIEW_THRESHOLD_REACHED" in text
        assert "bnss-479-v1" in text
        assert "critical_facts_verified" in text  # rule trace present
        assert "Counsel Reviewer" in text
        assert "Page 1 of" in text


def test_review_pack_without_evaluation_says_not_performed():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        _upload_blank_pdf(client, case_id)  # facts exist, but never evaluated
        resp = client.get(f"/api/cases/{case_id}/review-pack")
        assert resp.status_code == 200
        text = _pdf_text(resp.content)
        assert "No Section 479 BNSS evaluation has been performed" in text
        assert "REVIEW_THRESHOLD_REACHED" not in text
        assert "THRESHOLD_NOT_REACHED" not in text


def test_review_pack_case_with_no_document_uploaded_at_all():
    with TestClient(app) as client:
        # DEMO-CASE-003 never has a document uploaded in this test -> facts table empty
        resp = client.get("/api/cases/DEMO-CASE-003/review-pack")
        assert resp.status_code == 200
        text = _pdf_text(resp.content)
        assert "no document uploaded" in text.lower()


def test_review_pack_distinguishes_fact_statuses():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-004"
        pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("record.pdf", pdf_bytes, "application/pdf")},
        )
        fact_ids = {f["fact_type"]: f["id"] for f in resp.json()["facts"]}
        # custody_start_date is now "unverified" (extracted, not reviewed).
        # max_punishment etc. remain "unknown" (never found in the document).
        flagged = client.patch(
            f"/api/cases/{case_id}/facts/{fact_ids['exception_flags']}",
            json={"verification_status": "conflict", "reviewer": "Reviewer Y", "verification_note": "Unclear phrasing"},
        )
        assert flagged.status_code == 200

        review = client.get(f"/api/cases/{case_id}/review-pack")
        text = _pdf_text(review.content)
        assert "UNVERIFIED" in text
        assert "UNKNOWN" in text
        assert "CONFLICT" in text
        assert "Unclear phrasing" in text


def test_review_pack_includes_source_page_and_explanation():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-005"
        pdf_bytes = _make_pdf(
            [
                ["Custody start date: 10 January 2026"],
                ["Maximum punishment: 7 years imprisonment"],
            ]
        )
        resp = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("case-record.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200

        review = client.get(f"/api/cases/{case_id}/review-pack")
        text = _pdf_text(review.content)
        assert "case-record.pdf" in text
        assert "p.1" in text
        assert "p.2" in text


def test_review_pack_shows_gazette_warning_and_disclaimer():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-006"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        _run_evaluation(client, case_id)

        review = client.get(f"/api/cases/{case_id}/review-pack")
        text = _pdf_text(review.content)
        assert "NOT YET VERIFIED against the official Gazette" in text
        assert "NOT a judicial determination" in text
        assert "NOT a bail order" in text
        assert "NOT a release authorization" in text


def test_review_pack_missing_case_404():
    with TestClient(app) as client:
        resp = client.get("/api/cases/NOT-A-REAL-CASE/review-pack")
        assert resp.status_code == 404


def test_review_pack_repeated_downloads_do_not_modify_evaluation_history():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        _run_evaluation(client, case_id, reviewer="Reviewer One")

        before = client.get(f"/api/cases/{case_id}/evaluations").json()
        for _ in range(3):
            r = client.get(f"/api/cases/{case_id}/review-pack")
            assert r.status_code == 200
        after = client.get(f"/api/cases/{case_id}/evaluations").json()
        assert before == after
        assert len(after) == 1


def test_review_pack_existing_endpoints_still_work():
    with TestClient(app) as client:
        assert client.get("/api/cases").status_code == 200
        assert client.get("/api/metrics").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}


# --- Follow-up tasks ---


def _future_due(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_due(hours=24):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _create_followup(client, case_id="DEMO-CASE-001", **overrides):
    body = {
        "case_id": case_id,
        "title": "Review custody documents",
        "description": "Check the uploaded PDF for missing facts",
        "assigned_reviewer": "Reviewer A",
        "due_at": _future_due(),
    }
    body.update(overrides)
    resp = client.post("/api/followups", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_follow_up_success():
    with TestClient(app) as client:
        fu = _create_followup(client)
        assert fu["case_id"] == "DEMO-CASE-001"
        assert fu["status"] == "pending"
        assert fu["is_overdue"] is False
        assert fu["completed_at"] is None
        assert fu["completed_by"] is None
        assert fu["created_at"] == fu["updated_at"]


def test_create_follow_up_unknown_case_404():
    with TestClient(app) as client:
        resp = client.post(
            "/api/followups",
            json={"case_id": "NOT-A-REAL-CASE", "title": "X", "assigned_reviewer": "R", "due_at": _future_due()},
        )
        assert resp.status_code == 404


def test_create_follow_up_invalid_due_at_422():
    with TestClient(app) as client:
        resp = client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-001", "title": "X", "assigned_reviewer": "R", "due_at": "not-a-date"},
        )
        assert resp.status_code == 422


def test_create_follow_up_requires_title_and_reviewer():
    with TestClient(app) as client:
        no_title = client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-001", "title": "   ", "assigned_reviewer": "R", "due_at": _future_due()},
        )
        assert no_title.status_code == 422
        no_reviewer = client.post(
            "/api/followups",
            json={"case_id": "DEMO-CASE-001", "title": "X", "assigned_reviewer": "  ", "due_at": _future_due()},
        )
        assert no_reviewer.status_code == 422


def test_follow_up_overdue_timezone_boundary():
    with TestClient(app) as client:
        now_utc = datetime.now(timezone.utc)
        # True instant: 1 hour ago (should be overdue). Expressed in a +10:00
        # offset, its LOCAL wall-clock numbers read ~9 hours ahead of `now` --
        # a buggy implementation that compared raw/local numbers without
        # converting to UTC first would wrongly call this "not overdue".
        true_instant = now_utc - timedelta(hours=1)
        due_at_plus10 = true_instant.astimezone(timezone(timedelta(hours=10)))

        fu = _create_followup(client, title="TZ boundary check", due_at=due_at_plus10.isoformat())
        assert fu["is_overdue"] is True

        stored = datetime.fromisoformat(fu["due_at"])
        assert abs((stored - true_instant).total_seconds()) < 1

        overdue_list = client.get("/api/followups", params={"overdue": "true"}).json()
        assert any(f["id"] == fu["id"] for f in overdue_list)
        not_overdue_list = client.get("/api/followups", params={"overdue": "false"}).json()
        assert not any(f["id"] == fu["id"] for f in not_overdue_list)


def test_follow_up_overdue_false_when_completed_even_if_past_due():
    with TestClient(app) as client:
        fu = _create_followup(client, due_at=_past_due())
        assert fu["is_overdue"] is True
        completed = client.patch(
            f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "Reviewer A"}
        ).json()
        assert completed["is_overdue"] is False


def test_list_follow_ups_filters_status_reviewer_case():
    with TestClient(app) as client:
        a = _create_followup(client, case_id="DEMO-CASE-001", assigned_reviewer="Reviewer A")
        b = _create_followup(client, case_id="DEMO-CASE-002", assigned_reviewer="Reviewer B")
        client.patch(f"/api/followups/{b['id']}", json={"status": "in_progress"})

        by_case = client.get("/api/followups", params={"case_id": "DEMO-CASE-001"}).json()
        assert {f["id"] for f in by_case} == {a["id"]}

        by_reviewer = client.get("/api/followups", params={"reviewer": "Reviewer B"}).json()
        assert {f["id"] for f in by_reviewer} == {b["id"]}

        by_status = client.get("/api/followups", params={"status": "in_progress"}).json()
        assert {f["id"] for f in by_status} == {b["id"]}

        by_status_pending = client.get("/api/followups", params={"status": "pending"}).json()
        assert {f["id"] for f in by_status_pending} == {a["id"]}


def test_list_follow_ups_invalid_status_422():
    with TestClient(app) as client:
        resp = client.get("/api/followups", params={"status": "not-a-real-status"})
        assert resp.status_code == 422


def test_case_scoped_follow_ups_endpoint():
    with TestClient(app) as client:
        a = _create_followup(client, case_id="DEMO-CASE-001")
        _create_followup(client, case_id="DEMO-CASE-002")

        resp = client.get("/api/cases/DEMO-CASE-001/followups")
        assert resp.status_code == 200
        assert {f["id"] for f in resp.json()} == {a["id"]}

        missing = client.get("/api/cases/NOT-A-REAL-CASE/followups")
        assert missing.status_code == 404


def test_patch_follow_up_update_details_and_reassignment():
    with TestClient(app) as client:
        fu = _create_followup(client)
        new_due = _future_due(hours=48)
        updated = client.patch(
            f"/api/followups/{fu['id']}",
            json={"title": "Updated title", "assigned_reviewer": "Reviewer Z", "due_at": new_due},
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["title"] == "Updated title"
        assert body["assigned_reviewer"] == "Reviewer Z"
        assert body["status"] == "pending"
        assert body["updated_at"] != fu["updated_at"]
        assert body["completed_at"] is None


def test_patch_follow_up_start_then_complete_requires_reviewer():
    with TestClient(app) as client:
        fu = _create_followup(client)
        started = client.patch(f"/api/followups/{fu['id']}", json={"status": "in_progress"})
        assert started.status_code == 200
        assert started.json()["status"] == "in_progress"

        rejected = client.patch(f"/api/followups/{fu['id']}", json={"status": "completed"})
        assert rejected.status_code == 422

        completed = client.patch(
            f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "Reviewer Q"}
        )
        assert completed.status_code == 200
        body = completed.json()
        assert body["status"] == "completed"
        assert body["completed_by"] == "Reviewer Q"
        assert body["completed_at"] is not None


def test_patch_follow_up_cancel_requires_reviewer():
    with TestClient(app) as client:
        fu = _create_followup(client)
        rejected = client.patch(f"/api/followups/{fu['id']}", json={"status": "cancelled"})
        assert rejected.status_code == 422
        cancelled = client.patch(
            f"/api/followups/{fu['id']}", json={"status": "cancelled", "reviewer": "Reviewer Q"}
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["completed_by"] == "Reviewer Q"


def test_patch_follow_up_cannot_leave_terminal_state_but_can_still_be_edited():
    with TestClient(app) as client:
        fu = _create_followup(client)
        completed = client.patch(
            f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "Reviewer Q"}
        ).json()

        reopen = client.patch(f"/api/followups/{fu['id']}", json={"status": "pending"})
        assert reopen.status_code == 422

        # A plain detail edit afterward must not clear completion history.
        edited = client.patch(f"/api/followups/{fu['id']}", json={"title": "Typo fix"})
        assert edited.status_code == 200
        body = edited.json()
        assert body["title"] == "Typo fix"
        assert body["status"] == "completed"
        assert body["completed_at"] == completed["completed_at"]
        assert body["completed_by"] == completed["completed_by"]


def test_patch_follow_up_unknown_id_404():
    with TestClient(app) as client:
        resp = client.patch("/api/followups/999999", json={"title": "X"})
        assert resp.status_code == 404


def test_patch_follow_up_invalid_due_at_422():
    with TestClient(app) as client:
        fu = _create_followup(client)
        resp = client.patch(f"/api/followups/{fu['id']}", json={"due_at": "garbage"})
        assert resp.status_code == 422


def test_patch_follow_up_noop_does_not_log_audit_event():
    with TestClient(app) as client:
        fu = _create_followup(client)
        before_log = client.get(f"/api/cases/{fu['case_id']}/audit-log").json()

        noop = client.patch(f"/api/followups/{fu['id']}", json={})
        assert noop.status_code == 200
        assert noop.json() == fu

        after_log = client.get(f"/api/cases/{fu['case_id']}/audit-log").json()
        assert after_log == before_log


# --- Audit trail ---


def test_audit_log_records_followup_lifecycle():
    with TestClient(app) as client:
        fu = _create_followup(client, case_id="DEMO-CASE-001")
        client.patch(f"/api/followups/{fu['id']}", json={"status": "in_progress"})
        client.patch(f"/api/followups/{fu['id']}", json={"assigned_reviewer": "Reviewer Z"})
        client.patch(f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "Reviewer Z"})

        events = client.get("/api/cases/DEMO-CASE-001/audit-log").json()
        event_types = [e["event_type"] for e in events]  # newest first
        assert event_types == [
            "followup_completed",
            "followup_reassigned",
            "followup_started",
            "followup_created",
        ]
        for e in events:
            assert e["entity_id"] == str(fu["id"])
            assert e["case_id"] == "DEMO-CASE-001"


def test_audit_log_records_followup_cancellation():
    with TestClient(app) as client:
        fu = _create_followup(client, case_id="DEMO-CASE-002")
        client.patch(f"/api/followups/{fu['id']}", json={"status": "cancelled", "reviewer": "Reviewer Q"})
        events = client.get("/api/cases/DEMO-CASE-002/audit-log").json()
        assert events[0]["event_type"] == "followup_cancelled"
        assert events[0]["before"]["status"] == "pending"
        assert events[0]["after"]["status"] == "cancelled"


def test_audit_log_records_fact_verification_and_conflict_flag_and_resolve():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-003"
        pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "custody_start_date")

        verified = client.patch(
            f"/api/cases/{case_id}/facts/{fact['id']}",
            json={"verification_status": "verified", "reviewer": "Reviewer V"},
        )
        assert verified.status_code == 200

        flagged = client.patch(
            f"/api/cases/{case_id}/facts/{fact['id']}",
            json={"verification_status": "conflict", "reviewer": "Reviewer V", "verification_note": "disputed"},
        )
        assert flagged.status_code == 200

        resolved = client.patch(
            f"/api/cases/{case_id}/facts/{fact['id']}",
            json={"verification_status": "verified", "reviewer": "Reviewer V"},
        )
        assert resolved.status_code == 200

        events = client.get(f"/api/cases/{case_id}/audit-log").json()
        event_types = [e["event_type"] for e in events]  # newest first
        assert event_types == ["fact_conflict_resolved", "fact_conflict_flagged", "fact_verified"]
        assert all(e["entity_id"] == str(fact["id"]) for e in events)


def test_audit_log_records_fact_correction_without_status_change():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-004"
        pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "custody_start_date")

        client.patch(f"/api/cases/{case_id}/facts/{fact['id']}", json={"value": "2026-01-12"})
        events = client.get(f"/api/cases/{case_id}/audit-log").json()
        assert events[0]["event_type"] == "fact_corrected"
        assert events[0]["before"]["value"] == "2026-01-10"
        assert events[0]["after"]["value"] == "2026-01-12"


def test_audit_log_records_evaluation_run():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-005"
        start = (date.today() - timedelta(days=10)).isoformat()
        _setup_critical_facts(client, case_id, custody_start_date=start, max_punishment_years=10.0)
        ev = _run_evaluation(client, case_id, reviewer="Reviewer E")

        events = client.get(f"/api/cases/{case_id}/audit-log").json()
        eval_events = [e for e in events if e["event_type"] == "evaluation_run"]
        assert len(eval_events) == 1
        assert eval_events[0]["entity_id"] == str(ev["id"])
        assert eval_events[0]["actor"] == "Reviewer E"
        assert eval_events[0]["after"]["outcome"] == ev["outcome"]


def test_audit_log_records_case_status_change():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-006"
        resp = client.patch(f"/api/cases/{case_id}", json={"review_status": "reviewed", "reviewer": "Reviewer S"})
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "reviewed"

        events = client.get(f"/api/cases/{case_id}/audit-log").json()
        assert events[0]["event_type"] == "case_status_changed"
        assert events[0]["before"]["review_status"] == "in_review"
        assert events[0]["after"]["review_status"] == "reviewed"

        # No-op (same status again) must not log a duplicate event.
        client.patch(f"/api/cases/{case_id}", json={"review_status": "reviewed", "reviewer": "Reviewer S"})
        events_after = client.get(f"/api/cases/{case_id}/audit-log").json()
        assert len(events_after) == len(events)


def test_case_status_patch_requires_reviewer_and_unknown_case_404():
    with TestClient(app) as client:
        no_reviewer = client.patch("/api/cases/DEMO-CASE-001", json={"review_status": "reviewed", "reviewer": "  "})
        assert no_reviewer.status_code == 422
        missing = client.patch(
            "/api/cases/NOT-A-REAL-CASE", json={"review_status": "reviewed", "reviewer": "Reviewer S"}
        )
        assert missing.status_code == 404


def test_audit_log_is_append_only_and_ordered_newest_first():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        fu = _create_followup(client, case_id=case_id)
        client.patch(f"/api/followups/{fu['id']}", json={"status": "in_progress"})
        client.patch(f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "R"})

        events = client.get(f"/api/cases/{case_id}/audit-log").json()
        timestamps = [e["created_at"] for e in events]
        assert timestamps == sorted(timestamps, reverse=True)
        ids = [e["id"] for e in events]
        assert len(ids) == len(set(ids))  # every event is its own row, nothing merged/overwritten


def test_audit_log_unknown_case_404():
    with TestClient(app) as client:
        resp = client.get("/api/cases/NOT-A-REAL-CASE/audit-log")
        assert resp.status_code == 404


def test_audit_log_limit_and_offset():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        for i in range(5):
            _create_followup(client, case_id=case_id, title=f"Task {i}")

        page1 = client.get(f"/api/cases/{case_id}/audit-log", params={"limit": 2, "offset": 0}).json()
        page2 = client.get(f"/api/cases/{case_id}/audit-log", params={"limit": 2, "offset": 2}).json()
        assert len(page1) == 2
        assert len(page2) == 2
        assert {e["id"] for e in page1}.isdisjoint({e["id"] for e in page2})

        invalid = client.get(f"/api/cases/{case_id}/audit-log", params={"limit": 0})
        assert invalid.status_code == 422


# --- Phase 7: additional regression coverage ---


def test_preview_rejects_oversized_file():
    with TestClient(app) as client:
        oversized = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 100)
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("big.pdf", oversized, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "10 mb" in resp.json()["detail"].lower()


def test_preview_rejects_pdf_extension_with_non_pdf_content():
    # A client could lie with a ".pdf" filename; the magic-byte check must
    # still catch content that isn't actually a PDF.
    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("fake.pdf", b"not actually a pdf, just text", "application/pdf")},
        )
        assert resp.status_code == 400


def test_evaluations_and_audit_log_have_no_mutation_routes():
    # Immutability is enforced at the routing level, not just by database.py
    # having no update/delete function: there is no PATCH/PUT/DELETE
    # registered on either path at all.
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        for path in (f"/api/cases/{case_id}/evaluations", f"/api/cases/{case_id}/audit-log"):
            assert client.patch(path, json={}).status_code == 405
            assert client.put(path, json={}).status_code == 405
            assert client.delete(path).status_code == 405


def test_uploaded_documents_never_exposed_via_static_route():
    # There is no StaticFiles mount or file-serving route anywhere in this
    # app -- uploaded PDF bytes are processed in memory only. Guard against
    # one being added carelessly later.
    with TestClient(app) as client:
        pdf_bytes = _make_pdf([["Custody start date: 10 January 2026"]])
        client.post(
            "/api/documents/preview",
            data={"case_id": "DEMO-CASE-001"},
            files={"file": ("private-record.pdf", pdf_bytes, "application/pdf")},
        )
        for path in ("/private-record.pdf", "/uploads/private-record.pdf", "/static/private-record.pdf", "/files/private-record.pdf"):
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} should not be servable, got {resp.status_code}"


def test_full_cross_phase_workflow_integration():
    """One flowing end-to-end test across every phase's feature, mirroring
    the manual workflow verification: load case -> upload -> extract with
    page refs -> verify/flag -> blocked evaluation -> unblock -> escalated
    evaluation -> review pack -> follow-up lifecycle -> audit trail -> data
    still consistent. Exists so a future regression in how these features
    compose (not just each one in isolation) gets caught."""
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"

        # 1. Load existing case.
        assert client.get(f"/api/cases/{case_id}").status_code == 200

        # 2-3. Upload a synthetic PDF; confirm source-page references.
        pdf_bytes = _make_pdf(
            [
                ["Custody start date: 10 January 2023", "Current charges: Theft"],
                ["Maximum punishment: 7 years imprisonment", "Other pending cases: FIR 1/2020"],
            ]
        )
        preview = client.post(
            "/api/documents/preview", data={"case_id": case_id},
            files={"file": ("record.pdf", pdf_bytes, "application/pdf")},
        ).json()
        facts = {f["fact_type"]: f for f in preview["facts"]}
        assert facts["custody_start_date"]["source_page"] == 1
        assert facts["max_punishment"]["source_page"] == 2
        fact_ids = {k: v["id"] for k, v in facts.items()}

        # 4. Edit, verify, and flag a conflicting fact.
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['custody_start_date']}",
                     json={"verification_status": "verified", "reviewer": "Integration Reviewer"})
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['current_charges']}",
                     json={"verification_status": "conflict", "reviewer": "Integration Reviewer", "verification_note": "disputed"})

        # 5-6. Run evaluation -> blocked (current_charges isn't critical, but
        # the still-unverified critical facts must block it).
        blocked = client.post(f"/api/cases/{case_id}/evaluations", json={"reviewer": "Integration Reviewer"}).json()
        assert blocked["outcome"] == "BLOCKED_MISSING_FACTS"
        assert len(blocked["blockers"]) > 0

        # Unblock: verify the remaining 4 critical facts.
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['max_punishment_years']}",
                     json={"value": 7.0, "verification_status": "verified", "reviewer": "Integration Reviewer"})
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['death_or_life_punishment']}",
                     json={"value": False, "verification_status": "verified", "reviewer": "Integration Reviewer"})
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['exception_flags']}",
                     json={"value": [], "verification_status": "verified", "reviewer": "Integration Reviewer"})
        client.patch(f"/api/cases/{case_id}/facts/{fact_ids['other_pending_cases']}",
                     json={"verification_status": "verified", "reviewer": "Integration Reviewer"})
        ran = client.post(f"/api/cases/{case_id}/evaluations", json={"reviewer": "Integration Reviewer"}).json()
        assert ran["outcome"] == "ESCALATED_LEGAL_REVIEW"  # other_pending_cases is non-empty

        # 7. Generate and download the Counsel Review Pack.
        review = client.get(f"/api/cases/{case_id}/review-pack")
        assert review.status_code == 200
        assert review.content.startswith(b"%PDF")

        # 8. Follow-up lifecycle: create, edit, start, complete; create & cancel another.
        due = (date.today() + timedelta(days=2)).isoformat() + "T00:00:00+00:00"
        fu = client.post("/api/followups", json={
            "case_id": case_id, "title": "Chase missing document", "assigned_reviewer": "Integration Reviewer", "due_at": due,
        }).json()
        client.patch(f"/api/followups/{fu['id']}", json={"description": "Updated description"})
        client.patch(f"/api/followups/{fu['id']}", json={"status": "in_progress"})
        done = client.patch(f"/api/followups/{fu['id']}", json={"status": "completed", "reviewer": "Integration Reviewer"}).json()
        assert done["status"] == "completed"

        fu2 = client.post("/api/followups", json={
            "case_id": case_id, "title": "No longer needed", "assigned_reviewer": "Integration Reviewer", "due_at": due,
        }).json()
        cancelled = client.patch(f"/api/followups/{fu2['id']}", json={"status": "cancelled", "reviewer": "Integration Reviewer"}).json()
        assert cancelled["status"] == "cancelled"

        # 9. Audit events for all of the above.
        events = client.get(f"/api/cases/{case_id}/audit-log?limit=100").json()
        event_types = {e["event_type"] for e in events}
        assert {
            "fact_verified", "fact_conflict_flagged", "evaluation_run",
            "followup_created", "followup_updated", "followup_started",
            "followup_completed", "followup_cancelled",
        }.issubset(event_types)

        # 10. Data remains internally consistent: metrics reflect the same case.
        metrics = client.get("/api/metrics").json()
        assert metrics["follow_up_status_counts"]["completed"] >= 1
        assert metrics["follow_up_status_counts"]["cancelled"] >= 1

        # Existing phase-1/2 endpoints still untouched by any of the above.
        assert client.get("/api/cases").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}


# --- Phase 7: bugs found by adversarial review, now fixed and locked in ---


def test_patch_fact_rejects_nan_and_infinity_max_punishment_years():
    # NaN/Infinity pass a bare "value <= 0" check (NaN compares False to
    # everything; inf is not <= 0) and used to crash round() in rules.py with
    # an uncaught ValueError/OverflowError -> 500. Must be a clean 422.
    with TestClient(app) as client:
        case_id = "DEMO-CASE-001"
        fact_ids = _upload_blank_pdf(client, case_id)
        fid = fact_ids["max_punishment_years"]
        for bad in ("NaN", "Infinity", "-Infinity"):
            resp = client.patch(
                f"/api/cases/{case_id}/facts/{fid}",
                content=f'{{"value": {bad}, "verification_status": "verified", "reviewer": "X"}}'.encode(),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 422, f"{bad} should be rejected with 422, got {resp.status_code}: {resp.text}"


def test_patch_fact_rejects_absurdly_large_max_punishment_years():
    with TestClient(app) as client:
        case_id = "DEMO-CASE-002"
        fact_ids = _upload_blank_pdf(client, case_id)
        fid = fact_ids["max_punishment_years"]
        resp = client.patch(
            f"/api/cases/{case_id}/facts/{fid}",
            json={"value": 1e9, "verification_status": "verified", "reviewer": "X"},
        )
        assert resp.status_code == 422


def test_followup_due_at_extreme_value_returns_422_not_500():
    # A year-9999 datetime with a negative offset overflows when converted to
    # UTC (date value out of range) -- must be a clean 422, not a 500.
    with TestClient(app) as client:
        resp = client.post(
            "/api/followups",
            json={
                "case_id": "DEMO-CASE-003", "title": "Extreme date",
                "assigned_reviewer": "X", "due_at": "9999-12-31T23:59:59-14:00",
            },
        )
        assert resp.status_code == 422


def test_extraction_does_not_misattribute_punishment_citation_as_charges():
    # "section"/"ipc" alone used to be charge-keywords, so this punishment-
    # source line (no real charges line at all) used to get wrongly
    # attributed to current_charges instead of leaving it unknown.
    with TestClient(app) as client:
        pdf_bytes = _make_pdf([["Section 379 IPC provides for: imprisonment up to 7 years"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": "DEMO-CASE-004"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        facts = {f["fact_type"]: f for f in resp.json()["facts"]}
        assert facts["current_charges"]["value"] is None
        assert facts["current_charges"]["verification_status"] == "unknown"
        assert facts["max_punishment_source"]["value"] == "imprisonment up to 7 years"


def test_extraction_does_not_set_death_or_life_for_negated_sentence():
    with TestClient(app) as client:
        pdf_bytes = _make_pdf([["The offence does not carry death penalty or life imprisonment"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": "DEMO-CASE-005"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "death_or_life_punishment")
        assert fact["value"] is None
        assert fact["verification_status"] == "unknown"


def test_extraction_still_detects_death_or_life_without_negation():
    # Sanity check that the negation guard above doesn't also suppress a
    # genuine, non-negated death/life mention.
    with TestClient(app) as client:
        pdf_bytes = _make_pdf([["Section 302 IPC is punishable with death or life imprisonment"]])
        resp = client.post(
            "/api/documents/preview", data={"case_id": "DEMO-CASE-006"},
            files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        )
        fact = next(f for f in resp.json()["facts"] if f["fact_type"] == "death_or_life_punishment")
        assert fact["value"] is True
        assert fact["verification_status"] == "unverified"
