"""Exercise real model predictions, API validation, and the Streamlit fallback."""

from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from api import config, service
from api.main import create_app
from predict_ticket import MODEL_FILENAMES, PROJECT_DIR, load_ticket_models, predict_ticket


def sample_tickets():
    selected = []
    counts = Counter()
    with (PROJECT_DIR / "data" / "tickets.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if counts[row["category"]] < 3:
                selected.append(row["ticket_text"])
                counts[row["category"]] += 1
    assert len(selected) == 12 and set(counts.values()) == {3}
    return selected


TICKETS = sample_tickets()


@pytest.fixture(scope="session", autouse=True)
def unchanged_protected_files():
    def hashes():
        paths = [PROJECT_DIR / "train_model.py", PROJECT_DIR / "predict_ticket.py"]
        paths += [path for folder in ("data", "models")
                  for path in (PROJECT_DIR / folder).rglob("*") if path.is_file()]
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    before = hashes()
    yield
    assert hashes() == before, "Protected ML source, data, or artifacts changed during testing."


@pytest.fixture(scope="session")
def real_models():
    return load_ticket_models()


@pytest.fixture(scope="session")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def assert_parity(actual, expected):
    assert actual["category"]["label"] == expected["category"]
    assert actual["urgency"]["label"] == expected["urgency"]
    assert actual["category"]["confidence"] == expected["category_confidence"]
    assert actual["urgency"]["confidence"] == expected["urgency_confidence"]
    assert actual["category"]["probabilities"] == expected["category_probabilities"]
    assert actual["urgency"]["probabilities"] == expected["urgency_probabilities"]
    assert actual["decision"]["needs_review"] == expected["needs_manual_review"]
    assert actual["decision"]["reasons"] == expected["review_reasons"]
    assert actual["decision"]["suggested_queue"] == expected["suggested_queue"]
    assigned = None if expected["needs_manual_review"] else expected["queue"]
    assert actual["decision"]["assigned_queue"] == assigned
    assert actual["review_threshold"] == expected["confidence_threshold"]


@pytest.mark.parametrize("text", TICKETS, ids=[f"ticket-{i + 1}" for i in range(12)])
def test_prediction_parity(client, real_models, text):
    expected = predict_ticket(text, config.REVIEW_THRESHOLD, loaded_models=real_models)
    response = client.post("/api/triage", json={"text": text})
    assert response.status_code == 200
    assert_parity(response.json(), expected)


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_review_and_automatic_routing(client, real_models, monkeypatch, threshold):
    monkeypatch.setattr(config, "REVIEW_THRESHOLD", threshold)
    expected = predict_ticket(TICKETS[0], threshold, loaded_models=real_models)
    response = client.post("/api/triage", json={"text": TICKETS[0]})
    assert response.status_code == 200
    result = response.json()
    assert_parity(result, expected)
    assert result["decision"]["needs_review"] is (threshold == 1.0)
    if threshold == 1.0:
        assert result["decision"]["assigned_queue"] is None
        assert "Category confidence is below the threshold." in result["decision"]["reasons"]
        assert "Urgency confidence is below the threshold." in result["decision"]["reasons"]
    else:
        assert result["decision"]["assigned_queue"] == expected["suggested_queue"]


def test_threshold_equality_is_not_below_threshold(client, real_models, monkeypatch):
    prediction = predict_ticket(TICKETS[0], loaded_models=real_models)
    threshold = min(prediction["category_confidence"], prediction["urgency_confidence"])
    monkeypatch.setattr(config, "REVIEW_THRESHOLD", threshold)
    response = client.post("/api/triage", json={"text": TICKETS[0]})
    assert response.status_code == 200
    assert response.json()["decision"]["needs_review"] is False


def test_unknown_vocabulary_still_requires_review(client, real_models, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_THRESHOLD", 0.0)
    text = "zzzzqqqvxxxx zzzzqqqvxxxx"
    expected = predict_ticket(text, 0.0, loaded_models=real_models)
    response = client.post("/api/triage", json={"text": text})
    assert response.status_code == 200
    assert_parity(response.json(), expected)
    assert response.json()["decision"]["needs_review"] is True
    assert response.json()["decision"]["assigned_queue"] is None


@pytest.mark.parametrize("payload", [
    {}, {"text": ""}, {"text": " \n\t "}, {"text": "short"},
    {"text": "a" * (config.MAX_TEXT_LENGTH + 1)},
    {"text": None}, {"text": 123}, {"text": 1.5}, {"text": True},
    {"text": []}, {"text": {}}, [], "not an object",
    {"text": TICKETS[0], "extra": "rejected"},
    {"text": TICKETS[0], "review_threshold": 0.0},
    {"text": TICKETS[0], "confidence_threshold": 0.0},
])
def test_invalid_requests(client, payload):
    original_threshold = config.REVIEW_THRESHOLD
    response = client.post("/api/triage", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert config.REVIEW_THRESHOLD == original_threshold
    assert "input" not in response.json()["error"]


def test_malformed_json(client):
    response = client.post("/api/triage", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_formatting_only_text(client):
    response = client.post("/api/triage", json={"text": "<div> </div>"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TICKET"


@pytest.mark.parametrize("text", ["billing ok", "a" * config.MAX_TEXT_LENGTH])
def test_length_boundaries(client, text):
    assert client.post("/api/triage", json={"text": text}).status_code == 200


def test_surrounding_whitespace_is_trimmed(client, real_models):
    response = client.post("/api/triage", json={"text": f" \n{TICKETS[0]}\t "})
    assert response.status_code == 200
    expected = predict_ticket(TICKETS[0], config.REVIEW_THRESHOLD, loaded_models=real_models)
    assert_parity(response.json(), expected)


def test_evaluation_matches_original(client):
    original = json.loads(config.EVALUATION_PATH.read_bytes())
    response = client.get("/api/evaluation")
    assert response.status_code == 200
    assert response.json() == original


def test_evaluation_download_is_byte_identical(client):
    response = client.get("/api/evaluation/download")
    assert response.status_code == 200
    assert response.content == config.EVALUATION_PATH.read_bytes()
    assert 'attachment; filename="evaluation.json"' == response.headers["content-disposition"]


@pytest.mark.parametrize("endpoint", ["/api/evaluation", "/api/evaluation/download"])
def test_missing_evaluation(client, monkeypatch, tmp_path, endpoint):
    monkeypatch.setattr(config, "EVALUATION_PATH", tmp_path / "not-present.json")
    response = client.get(endpoint)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVALUATION_MISSING"
    assert str(tmp_path) not in response.text
    assert client.post("/api/triage", json={"text": TICKETS[0]}).status_code == 200


def test_invalid_evaluation(client, monkeypatch, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(config, "EVALUATION_PATH", path)
    response = client.get("/api/evaluation")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EVALUATION_INVALID"


def test_unreadable_evaluation(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "EVALUATION_PATH", tmp_path)
    response = client.get("/api/evaluation")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EVALUATION_UNAVAILABLE"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "models_loaded": True,
        "review_threshold": config.REVIEW_THRESHOLD,
        "models": {"category": True, "urgency": True},
    }


@pytest.mark.parametrize("corrupt_files", [False, True])
def test_missing_or_unreadable_models(monkeypatch, tmp_path, corrupt_files):
    if corrupt_files:
        for name in MODEL_FILENAMES:
            (tmp_path / name).write_bytes(b"not a joblib artifact")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    with TestClient(create_app()) as missing_client:
        for method, endpoint, kwargs in (
            ("get", "/api/health", {}),
            ("post", "/api/triage", {"json": {"text": TICKETS[0]}}),
        ):
            response = getattr(missing_client, method)(endpoint, **kwargs)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "MODELS_MISSING"
            assert str(tmp_path) not in response.text
        assert missing_client.get("/api/evaluation").status_code == 200


def test_models_load_once_per_startup(monkeypatch):
    calls = []
    original_loader = service.load_ticket_models

    def counted_loader(path):
        calls.append(path)
        return original_loader(path)

    monkeypatch.setattr(service, "load_ticket_models", counted_loader)
    with TestClient(create_app()) as cached_client:
        for text in TICKETS[:2]:
            assert cached_client.post("/api/triage", json={"text": text}).status_code == 200
        assert cached_client.get("/api/health").status_code == 200
    assert len(calls) == 1


def test_prediction_errors_are_sanitized(client, monkeypatch):
    def broken_prediction(*args, **kwargs):
        raise RuntimeError("sensitive-path-and-ticket-content")

    monkeypatch.setattr(service, "predict_ticket", broken_prediction)
    response = client.post("/api/triage", json={"text": TICKETS[0]})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PREDICTION_FAILED"
    assert "sensitive-path-and-ticket-content" not in response.text
    assert TICKETS[0] not in response.text


@pytest.mark.parametrize("origin,allowed", [
    ("http://localhost:5173", True), ("http://127.0.0.1:5173", True),
    ("https://unapproved.example", False),
])
def test_restricted_cors(client, origin, allowed):
    headers = {"Origin": origin, "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "Content-Type"}
    response = client.options("/api/triage", headers=headers)
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)


def test_optional_frontend_and_api_isolation(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>future frontend</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('asset');", encoding="utf-8")
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path)
    with TestClient(create_app()) as spa_client:
        for route in ("/", "/tickets/123"):
            response = spa_client.get(route)
            assert response.status_code == 200
            assert "future frontend" in response.text
        assert spa_client.get("/assets/app.js").status_code == 200
        assert spa_client.get("/assets/missing.js").status_code == 404
        assert spa_client.get("/api/not-a-route").status_code == 404
        assert spa_client.get("/api").status_code == 404
        assert spa_client.get("/api/health").json()["models_loaded"] is True
        assert spa_client.get("/api/evaluation").status_code == 200
        assert spa_client.get("/api/openapi.json").status_code == 200
        assert spa_client.post("/api/triage", json={"text": TICKETS[0]}).status_code == 200
        assert spa_client.get("/%2e%2e/README.md").status_code == 404


def test_api_starts_without_frontend(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path / "absent-dist")
    with TestClient(create_app()) as api_client:
        assert api_client.get("/api/health").status_code == 200
        assert api_client.get("/").status_code == 404


def test_all_backend_routes_use_api_prefix(client):
    for route in client.app.routes:
        if hasattr(route, "methods"):
            assert route.path.startswith("/api/")
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/docs/oauth2-redirect").status_code == 200


@pytest.mark.parametrize("value", ["not-a-number", "nan", "inf", "-0.01", "1.01"])
def test_invalid_threshold_configuration(value):
    environment = dict(os.environ, REVIEW_THRESHOLD=value)
    process = subprocess.run(
        [sys.executable, "-B", "-c", "import api.config"], cwd=PROJECT_DIR,
        env=environment, capture_output=True, text=True,
    )
    assert process.returncode != 0
    assert "REVIEW_THRESHOLD must be a finite number between 0 and 1." in process.stderr


def test_environment_configuration(tmp_path):
    evaluation_path = tmp_path / "saved.json"
    environment = dict(os.environ, REVIEW_THRESHOLD="0.75", EVALUATION_PATH=str(evaluation_path))
    script = (
        "import json; from api import config; "
        "print(json.dumps([config.REVIEW_THRESHOLD, str(config.EVALUATION_PATH)]))"
    )
    process = subprocess.run(
        [sys.executable, "-B", "-c", script], cwd=PROJECT_DIR, env=environment,
        capture_output=True, text=True, check=True,
    )
    assert json.loads(process.stdout) == [0.75, str(evaluation_path)]


def test_streamlit_fallback(real_models):
    from streamlit.testing.v1 import AppTest

    dashboard = AppTest.from_file(str(PROJECT_DIR / "app.py")).run(timeout=30)
    assert not dashboard.exception
    assert len(dashboard.slider) == 0
    assert {tab.label for tab in dashboard.tabs} >= {"Ticket triage", "Model performance"}
    dashboard.text_area[0].input(TICKETS[0])
    dashboard.button[0].click().run(timeout=30)
    assert not dashboard.exception
    expected = predict_ticket(TICKETS[0], config.REVIEW_THRESHOLD, loaded_models=real_models)
    metrics = {metric.label: metric.value for metric in dashboard.metric}
    assert metrics["Category"] == expected["category"]
    assert metrics["Urgency"] == expected["urgency"]
    assert dashboard.session_state["prediction_result"] == expected
    assert dashboard.session_state["prediction_result"]["confidence_threshold"] == config.REVIEW_THRESHOLD
