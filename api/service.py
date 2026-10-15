"""Load artifacts and adapt existing predictions; no training or ML rewrite."""

import json
import logging

from api import config
from predict_ticket import load_ticket_models, predict_ticket


LOGGER = logging.getLogger(__name__)


class ServiceError(Exception):
    """A safe public error, with no original exception text or local paths."""

    def __init__(self, status_code, code, message):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def models_missing_error():
    return ServiceError(
        503, "MODELS_MISSING",
        "Provide the trusted vectorizer and both classifier .joblib files in models/ "
        "from the same training run, use compatible dependencies, and restart the API.",
    )


def load_models():
    """Called once per application startup; leave API available if loading fails."""
    try:
        return load_ticket_models(config.MODELS_DIR)
    except Exception as error:
        # Do not log exception messages: they may contain sensitive local paths.
        LOGGER.error("Model startup failed (%s)", type(error).__name__)
        return None


def triage_ticket(text, models):
    try:
        result = predict_ticket(
            text, confidence_threshold=config.REVIEW_THRESHOLD, loaded_models=models
        )
    except ValueError:
        raise ServiceError(
            422, "INVALID_TICKET",
            "Ticket text must contain letters or numbers after formatting is removed.",
        ) from None
    except Exception as error:
        LOGGER.error("Prediction failed (%s)", type(error).__name__)
        raise ServiceError(
            500, "PREDICTION_FAILED",
            "Prediction could not be completed. Ask the server administrator to check model compatibility.",
        ) from None

    # Adapt public field names without changing classification or review logic.
    return {
        "category": {
            "label": result["category"],
            "confidence": result["category_confidence"],
            "probabilities": result["category_probabilities"],
        },
        "urgency": {
            "label": result["urgency"],
            "confidence": result["urgency_confidence"],
            "probabilities": result["urgency_probabilities"],
        },
        "decision": {
            "needs_review": result["needs_manual_review"],
            "reasons": result["review_reasons"],
            "assigned_queue": None if result["needs_manual_review"] else result["queue"],
            "suggested_queue": result["suggested_queue"],
        },
        "review_threshold": result["confidence_threshold"],
    }


def read_evaluation_bytes():
    """Read the saved file verbatim, including for downloads."""
    try:
        return config.EVALUATION_PATH.read_bytes()
    except FileNotFoundError:
        raise ServiceError(
            404, "EVALUATION_MISSING",
            "Provide the saved evaluation.json from the model training run in models/ "
            "or configure EVALUATION_PATH to point to it.",
        ) from None
    except OSError:
        raise ServiceError(
            503, "EVALUATION_UNAVAILABLE",
            "The saved evaluation cannot be read. Ask the administrator to check the file and its permissions.",
        ) from None


def read_evaluation():
    data = read_evaluation_bytes()
    try:
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Expected an object")
        return result
    except (ValueError, UnicodeError):
        raise ServiceError(
            503, "EVALUATION_INVALID",
            "The saved evaluation is not a valid JSON object. Restore the original training evaluation file.",
        ) from None
