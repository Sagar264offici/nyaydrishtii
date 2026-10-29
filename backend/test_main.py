from datetime import date

from fastapi.testclient import TestClient

from main import app


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

        expected_overdue = sum(
            1
            for c in cases
            if c["next_follow_up"] and date.fromisoformat(c["next_follow_up"]) < date.today()
        )
        assert metrics["overdue_follow_ups"] == expected_overdue
