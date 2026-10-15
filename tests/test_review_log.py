"""Exercise private review storage with genuine predictions and temporary JSONL."""

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from api import config, review_log
from api.main import create_app
from predict_ticket import PROJECT_DIR, load_ticket_models, predict_ticket


with (PROJECT_DIR / "data" / "tickets.csv").open(encoding="utf-8", newline="") as handle:
    EXAMPLE_TICKET = next(csv.DictReader(handle))["ticket_text"]

REQUIRED_FIELDS = {
    "ticket_id", "timestamp", "ticket_text", "category", "category_confidence",
    "urgency", "urgency_confidence", "reasons", "suggested_queue", "status",
}


@pytest.fixture(scope="module")
def review_client():
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture(scope="module")
def models():
    return load_ticket_models()


def administrator_headers():
    return {"Authorization": f"Bearer {config.ADMIN_REVIEW_TOKEN}"}


def read_records(path):
    if not path.exists():
        return []
    contents = path.read_text(encoding="utf-8")
    assert contents.endswith("\n"), "Written JSONL snapshots need complete record lines."
    return [json.loads(line) for line in contents.splitlines()]


def submit_for_review(client, text=EXAMPLE_TICKET):
    response = client.post("/api/triage", json={"text": text})
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["needs_review"] is True
    return response.json()


def assert_private_response(response):
    assert "no-store" in response.headers.get("cache-control", "")


def assert_record_matches(record, text, prediction):
    assert set(record) == REQUIRED_FIELDS
    assert record["ticket_text"] == text
    assert record["category"] == prediction["category"]
    assert record["category_confidence"] == prediction["category_confidence"]
    assert record["urgency"] == prediction["urgency"]
    assert record["urgency_confidence"] == prediction["urgency_confidence"]
    assert record["reasons"] == prediction["review_reasons"]
    assert record["suggested_queue"] == prediction["suggested_queue"]
    assert record["status"] == "pending"
    assert str(UUID(record["ticket_id"])) == record["ticket_id"]
    timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    assert timestamp.utcoffset() == timezone.utc.utcoffset(timestamp)
    assert timestamp <= datetime.now(timezone.utc)


def test_review_record_matches_real_prediction_and_preserves_original_text(
    review_client, models, isolated_review_log,
):
    text = f" \n{EXAMPLE_TICKET}\t "
    expected = predict_ticket(text, config.REVIEW_THRESHOLD, loaded_models=models)
    assert expected["needs_manual_review"] is True
    result = submit_for_review(review_client, text)
    record, = read_records(isolated_review_log)
    assert_record_matches(record, text, expected)
    assert result["category"]["confidence"] == record["category_confidence"]
    assert result["urgency"]["confidence"] == record["urgency_confidence"]
    assert result["decision"]["assigned_queue"] is None


def test_automatically_routed_ticket_is_not_logged(
    review_client, models, isolated_review_log, monkeypatch,
):
    # Test the automatically routed branch with an explicit test-only threshold.
    # Predictions and probabilities still come from the original trained models.
    monkeypatch.setattr(config, "REVIEW_THRESHOLD", 0.0)
    expected = predict_ticket(EXAMPLE_TICKET, 0.0, loaded_models=models)
    assert expected["needs_manual_review"] is False
    response = review_client.post("/api/triage", json={"text": EXAMPLE_TICKET})
    assert response.status_code == 200
    assert response.json()["decision"]["assigned_queue"] == expected["suggested_queue"]
    assert read_records(isolated_review_log) == []


def test_public_triage_works_with_review_access_disabled(review_client, monkeypatch, isolated_review_log):
    monkeypatch.setattr(config, "ADMIN_REVIEW_TOKEN", "")
    submit_for_review(review_client)
    assert len(read_records(isolated_review_log)) == 1


@pytest.mark.parametrize("authorization", [
    None, "", "Bearer", "Bearer incorrect-token", "Basic incorrect-token",
    "Token incorrect-token", "Bearer incorrect token",
])
def test_missing_or_invalid_credentials_cannot_read_records(
    review_client, isolated_review_log, authorization,
):
    submit_for_review(review_client)
    headers = {} if authorization is None else {"Authorization": authorization}
    response = review_client.get("/api/review-log", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert EXAMPLE_TICKET not in response.text
    assert config.ADMIN_REVIEW_TOKEN not in response.text
    assert str(isolated_review_log) not in response.text
    assert_private_response(response)


@pytest.mark.parametrize("token", [None, "", " \t "])
def test_unconfigured_administrator_access_is_disabled(review_client, monkeypatch, token):
    monkeypatch.setattr(config, "ADMIN_REVIEW_TOKEN", token)
    response = review_client.get("/api/review-log", headers={"Authorization": "Bearer supplied-token"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REVIEW_ACCESS_DISABLED"
    assert "ADMIN_REVIEW_TOKEN" in response.json()["error"]["message"]
    assert_private_response(response)


def test_non_ascii_configured_token_cannot_cause_comparison_exception(review_client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REVIEW_TOKEN", "administrateur-\u00e9ph\u00e9m\u00e8re")
    response = review_client.get("/api/review-log", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert_private_response(response)


@pytest.mark.parametrize("create_empty_file", [False, True])
def test_missing_or_empty_logs_return_empty_page(review_client, isolated_review_log, create_empty_file):
    if create_empty_file:
        isolated_review_log.parent.mkdir(parents=True)
        isolated_review_log.write_text("", encoding="utf-8")
    response = review_client.get("/api/review-log", headers=administrator_headers())
    assert response.status_code == 200
    assert response.json() == {
        "items": [], "page": 1, "page_size": config.REVIEW_LOG_PAGE_SIZE,
        "total": 0, "total_pages": 0,
    }
    assert_private_response(response)


def test_administrator_can_page_newest_records_first(review_client, isolated_review_log):
    for index in range(7):
        submit_for_review(review_client, f"{EXAMPLE_TICKET}\nSubmission {index}.")
    stored = read_records(isolated_review_log)
    identifiers = [record["ticket_id"] for record in stored]
    assert len(set(identifiers)) == 7
    actual = []
    for page in range(1, 4):
        response = review_client.get(
            "/api/review-log", params={"page": page, "page_size": 3},
            headers=administrator_headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["page"], body["page_size"], body["total"], body["total_pages"]) == (page, 3, 7, 3)
        actual.extend(item["ticket_id"] for item in body["items"])
        assert_private_response(response)
    assert actual == list(reversed(identifiers))
    response = review_client.get(
        "/api/review-log?page=4&page_size=3", headers=administrator_headers(),
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.parametrize("query", [
    "page=0", "page=-1", "page=abc", "page_size=0", "page_size=-1",
    "page_size=101", "page_size=abc",
])
def test_invalid_pagination_is_rejected_privately(review_client, query):
    response = review_client.get(f"/api/review-log?{query}", headers=administrator_headers())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert_private_response(response)


def test_corruption_is_not_exposed_to_unauthorized_visitors(review_client, isolated_review_log):
    isolated_review_log.parent.mkdir(parents=True)
    isolated_review_log.write_text("sensitive-damaged-ticket-record", encoding="utf-8")
    response = review_client.get("/api/review-log")
    assert response.status_code == 401
    assert "sensitive-damaged-ticket-record" not in response.text


@pytest.mark.parametrize("corruption", [
    "invalid-json", "array", "missing-field", "invalid-confidence",
    "invalid-timestamp", "invalid-ticket-id", "invalid-status", "invalid-reasons",
])
def test_corrupted_logs_fail_safely_without_overwriting_records(
    review_client, isolated_review_log, corruption,
):
    submit_for_review(review_client)
    record, = read_records(isolated_review_log)
    if corruption == "invalid-json":
        damaged = '{"ticket_text": "private-incomplete-record"'
    elif corruption == "array":
        damaged = "[]"
    else:
        if corruption == "missing-field":
            del record["urgency"]
        elif corruption == "invalid-confidence":
            record["category_confidence"] = 1.1
        elif corruption == "invalid-timestamp":
            record["timestamp"] = "2026-10-15T09:30:00"  # Missing UTC offset.
        elif corruption == "invalid-ticket-id":
            record["ticket_id"] = "not-a-uuid"
        elif corruption == "invalid-status":
            record["status"] = "fabricated-status"
        elif corruption == "invalid-reasons":
            record["reasons"] = "not-a-list"
        damaged = json.dumps(record)
    isolated_review_log.write_text(damaged + "\n", encoding="utf-8")
    before = isolated_review_log.read_bytes()
    for response in (
        review_client.get("/api/review-log", headers=administrator_headers()),
        review_client.post("/api/triage", json={"text": EXAMPLE_TICKET}),
    ):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "REVIEW_LOG_CORRUPTED"
        assert EXAMPLE_TICKET not in response.text
        assert str(isolated_review_log) not in response.text
    assert isolated_review_log.read_bytes() == before


@pytest.mark.parametrize("failure", [
    PermissionError("private-path-denied"), OSError(errno.ENOSPC, "private-disk-full"),
])
def test_write_failures_leave_complete_prior_snapshot_and_sanitize_errors(
    review_client, isolated_review_log, monkeypatch, failure,
):
    submit_for_review(review_client)
    before = isolated_review_log.read_bytes()

    def fail_replace(*args, **kwargs):
        raise failure

    monkeypatch.setattr(review_log.os, "replace", fail_replace)
    response = review_client.post("/api/triage", json={"text": EXAMPLE_TICKET})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REVIEW_LOG_UNAVAILABLE"
    assert EXAMPLE_TICKET not in response.text
    assert str(failure) not in response.text
    assert str(isolated_review_log) not in response.text
    assert isolated_review_log.read_bytes() == before
    assert len(read_records(isolated_review_log)) == 1


def test_unreadable_log_returns_safe_private_error(review_client, isolated_review_log, monkeypatch):
    submit_for_review(review_client)
    original_open = Path.open

    def fail_record_open(path, *args, **kwargs):
        if path == isolated_review_log:
            raise PermissionError("sensitive-file-and-ticket-details")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_record_open)
    response = review_client.get("/api/review-log", headers=administrator_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REVIEW_LOG_UNAVAILABLE"
    assert "sensitive-file-and-ticket-details" not in response.text
    assert str(isolated_review_log) not in response.text
    assert_private_response(response)


def test_concurrent_threads_log_every_genuine_prediction_once(review_client, models, isolated_review_log):
    texts = [f"{EXAMPLE_TICKET}\nConcurrent submission {index}." for index in range(12)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda text: submit_for_review(review_client, text), texts))
    records = read_records(isolated_review_log)
    assert len(records) == len(results) == 12
    assert len({record["ticket_id"] for record in records}) == 12
    assert {record["ticket_text"] for record in records} == set(texts)
    for record in records:
        expected = predict_ticket(record["ticket_text"], config.REVIEW_THRESHOLD, loaded_models=models)
        assert_record_matches(record, record["ticket_text"], expected)


def test_concurrent_processes_share_safe_complete_jsonl_storage(models, isolated_review_log):
    script = """
import json, sys
from fastapi.testclient import TestClient
from api.main import create_app
with TestClient(create_app()) as client:
    for index in range(3):
        text = sys.argv[1] + '\\nProcess ' + sys.argv[2] + ' submission ' + str(index) + '.'
        response = client.post('/api/triage', json={'text': text})
        assert response.status_code == 200, response.text
        assert response.json()['decision']['needs_review'] is True
print('three genuine predictions saved')
"""
    processes = []
    try:
        for index in range(4):
            processes.append(subprocess.Popen(
                [sys.executable, "-B", "-c", script, EXAMPLE_TICKET, str(index)],
                cwd=PROJECT_DIR, env=dict(os.environ), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ))
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            assert process.returncode == 0, stderr
            assert "three genuine predictions saved" in stdout
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    records = read_records(isolated_review_log)
    assert len(records) == 12
    assert len({record["ticket_id"] for record in records}) == 12
    assert len({record["ticket_text"] for record in records}) == 12
    for record in records:
        expected = predict_ticket(record["ticket_text"], config.REVIEW_THRESHOLD, loaded_models=models)
        assert_record_matches(record, record["ticket_text"], expected)


def test_static_routes_cannot_expose_review_records(review_client, isolated_review_log):
    submit_for_review(review_client)
    for route in (
        "/logs/manual_review.jsonl", "/logs/manual_review.jsonl.lock",
        "/assets/../../logs/manual_review.jsonl",
        "/%2e%2e/logs/manual_review.jsonl",
    ):
        response = review_client.get(route)
        assert response.status_code == 404
        assert EXAMPLE_TICKET not in response.text
    # A directory-style SPA route may return the public index document; it must
    # still never turn into a directory listing or expose any private record.
    response = review_client.get("/logs/")
    assert response.status_code in (200, 404)
    assert EXAMPLE_TICKET not in response.text
    assert "manual_review.jsonl" not in response.text


def test_api_documents_input_bounds_and_counts_unicode_code_points(review_client, isolated_review_log):
    schema = review_client.get("/api/openapi.json").json()
    text_schema = schema["components"]["schemas"]["TriageRequest"]["properties"]["text"]
    assert text_schema["maxLength"] == config.MAX_TEXT_LENGTH
    assert text_schema["minLength"] == config.MIN_TEXT_LENGTH
    # Astral characters use two UTF-16 units in JS, but one Python code point.
    exact = "billing " + "\U0001f642" * (config.MAX_TEXT_LENGTH - len("billing "))
    assert len(exact) == config.MAX_TEXT_LENGTH
    assert review_client.post("/api/triage", json={"text": exact}).status_code == 200
    response = review_client.post("/api/triage", json={"text": exact + "\U0001f642"})
    assert response.status_code == 422


def test_review_environment_configuration_is_server_side_and_resolved(tmp_path):
    path = tmp_path / "configured.jsonl"
    environment = dict(
        os.environ, REVIEW_LOG_PATH=str(path), ADMIN_REVIEW_TOKEN="temporary-config-test-token",
        REVIEW_LOG_PAGE_SIZE="7",
    )
    script = (
        "import json; from api import config; "
        "print(json.dumps([str(config.REVIEW_LOG_PATH), config.REVIEW_LOG_PAGE_SIZE, "
        "config.ADMIN_REVIEW_TOKEN == 'temporary-config-test-token']))"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], cwd=PROJECT_DIR, env=environment,
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [str(path), 7, True]
