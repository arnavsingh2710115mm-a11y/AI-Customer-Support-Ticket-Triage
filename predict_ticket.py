"""Classify a new ticket and route uncertain predictions to manual review."""

import argparse
import json
from pathlib import Path

import joblib

from train_model import PROJECT_DIR, clean_ticket_text


SUPPORT_QUEUES = {
    "Billing": "Billing Support",
    "Technical": "Technical Support",
    "Account": "Account Support",
    "Product": "Product Support",
}
DEFAULT_CONFIDENCE_THRESHOLD = 0.60
MODEL_FILENAMES = (
    "tfidf_vectorizer.joblib", "category_model.joblib", "urgency_model.joblib"
)


def load_ticket_models(models_dir=PROJECT_DIR / "models"):
    """Load trusted local artifacts; dashboards can cache the returned tuple."""
    models_dir = Path(models_dir)
    missing = [name for name in MODEL_FILENAMES if not (models_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing model artifacts: {', '.join(missing)}. "
            "Copy the trained files into models/ or run train_model.py manually."
        )
    return tuple(joblib.load(models_dir / name) for name in MODEL_FILENAMES)


def predict_ticket(ticket_text, confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
                   models_dir=PROJECT_DIR / "models", loaded_models=None):
    """Return labels, probability scores, and routing for one customer ticket.

    Scores are model probabilities, not a guarantee of correctness. Choose a
    threshold using representative real-world validation data before deployment.
    Only load Joblib artifacts created locally or from a trusted source.
    Optionally supply the tuple from load_ticket_models to reuse cached models.
    """
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be between 0 and 1.")
    cleaned_text = clean_ticket_text(ticket_text)
    if not cleaned_text or not any(character.isalnum() for character in cleaned_text):
        raise ValueError("Ticket text must be a nonempty string containing letters or numbers.")

    if loaded_models is None:
        loaded_models = load_ticket_models(models_dir)
    vectorizer, category_model, urgency_model = loaded_models
    features = vectorizer.transform([cleaned_text])

    category_probabilities = category_model.predict_proba(features)[0]
    urgency_probabilities = urgency_model.predict_proba(features)[0]
    category_index = category_probabilities.argmax()
    urgency_index = urgency_probabilities.argmax()
    category = str(category_model.classes_[category_index])
    urgency = str(urgency_model.classes_[urgency_index])
    category_confidence = float(category_probabilities[category_index])
    urgency_confidence = float(urgency_probabilities[urgency_index])

    review_reasons = []
    if category_confidence < confidence_threshold:
        review_reasons.append("Category confidence is below the threshold.")
    if urgency_confidence < confidence_threshold:
        review_reasons.append("Urgency confidence is below the threshold.")
    if features.nnz == 0:
        review_reasons.append("Ticket has no vocabulary recognized by the trained vectorizer.")
    needs_manual_review = bool(review_reasons)
    suggested_queue = SUPPORT_QUEUES[category]

    return {
        "category": category,
        "urgency": urgency,
        "category_confidence": category_confidence,
        "urgency_confidence": urgency_confidence,
        "category_probabilities": dict(zip(
            category_model.classes_.tolist(), category_probabilities.tolist()
        )),
        "urgency_probabilities": dict(zip(
            urgency_model.classes_.tolist(), urgency_probabilities.tolist()
        )),
        "queue": "Manual Review" if needs_manual_review else suggested_queue,
        "suggested_queue": suggested_queue,
        "needs_manual_review": needs_manual_review,
        "review_reasons": review_reasons,
        "confidence_threshold": confidence_threshold,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket_text", help="Customer ticket text enclosed in quotes")
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--models-dir", type=Path, default=PROJECT_DIR / "models")
    args = parser.parse_args()
    try:
        result = predict_ticket(args.ticket_text, args.threshold, args.models_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Prediction failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
