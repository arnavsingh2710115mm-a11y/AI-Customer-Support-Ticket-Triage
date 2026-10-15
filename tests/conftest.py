"""Keep every API test, including legacy parity checks, away from real records."""

from pathlib import Path

import pytest

from api import config


TEST_REVIEW_TOKEN = "temporary-administrator-token-for-tests"


@pytest.fixture(autouse=True)
def isolated_review_log(monkeypatch, tmp_path_factory):
    """Also export the path so child Python processes share this test's log."""
    # Keep this separate from tmp_path: legacy static-serving tests deliberately
    # configure tmp_path as a public frontend directory, where private logs are
    # correctly forbidden.
    path = tmp_path_factory.mktemp("private-review-log") / "records" / "manual_review.jsonl"
    monkeypatch.setattr(config, "REVIEW_LOG_PATH", path)
    monkeypatch.setattr(config, "ADMIN_REVIEW_TOKEN", TEST_REVIEW_TOKEN)
    monkeypatch.setenv("REVIEW_LOG_PATH", str(path))
    monkeypatch.setenv("ADMIN_REVIEW_TOKEN", TEST_REVIEW_TOKEN)
    return path


@pytest.fixture(scope="session", autouse=True)
def preserve_real_review_records():
    """Catch accidental records or lock files outside the temporary test folders."""
    real_directory = Path(config.PROJECT_DIR) / "logs"

    def snapshot():
        if not real_directory.exists():
            return None
        return {
            str(path.relative_to(real_directory)): path.read_bytes()
            for path in real_directory.rglob("*") if path.is_file()
        }

    before = snapshot()
    yield
    assert snapshot() == before, "Tests changed the real logs directory."
