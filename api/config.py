"""Server-controlled configuration, shared with the Streamlit fallback."""

import math
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_DIR / "models"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

try:
    REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.60"))
except ValueError:
    raise ValueError("REVIEW_THRESHOLD must be a finite number between 0 and 1.") from None
if not math.isfinite(REVIEW_THRESHOLD) or not 0 <= REVIEW_THRESHOLD <= 1:
    raise ValueError("REVIEW_THRESHOLD must be a finite number between 0 and 1.")

evaluation_setting = os.getenv("EVALUATION_PATH", "models/evaluation.json").strip()
if not evaluation_setting:
    raise ValueError("EVALUATION_PATH must not be empty.")
EVALUATION_PATH = Path(evaluation_setting).expanduser()
if not EVALUATION_PATH.is_absolute():
    EVALUATION_PATH = PROJECT_DIR / EVALUATION_PATH

# Streamlit already permits 20,000 characters but defines no explicit minimum.
MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 20000
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Administrator access is optional. Public classification never requires it.
ADMIN_REVIEW_TOKEN = os.getenv("ADMIN_REVIEW_TOKEN", "")
review_log_setting = os.getenv("REVIEW_LOG_PATH", "logs/manual_review.jsonl").strip()
REVIEW_LOG_PATH = Path(review_log_setting).expanduser() if review_log_setting else None
if REVIEW_LOG_PATH is not None and not REVIEW_LOG_PATH.is_absolute():
    REVIEW_LOG_PATH = PROJECT_DIR / REVIEW_LOG_PATH

REVIEW_LOG_MAX_PAGE_SIZE = 100
try:
    REVIEW_LOG_PAGE_SIZE = int(os.getenv("REVIEW_LOG_PAGE_SIZE", "20"))
except ValueError:
    raise ValueError("REVIEW_LOG_PAGE_SIZE must be an integer from 1 to 100.") from None
if not 1 <= REVIEW_LOG_PAGE_SIZE <= REVIEW_LOG_MAX_PAGE_SIZE:
    raise ValueError("REVIEW_LOG_PAGE_SIZE must be an integer from 1 to 100.")
