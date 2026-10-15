"""Train and evaluate ticket classifiers using clearly labeled synthetic data.

Run manually with Python 3.12 in the ticket_ai Conda environment.
Synthetic test results do not establish real-world accuracy.
"""

import argparse
import html
import json
from pathlib import Path
import re

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split


PROJECT_DIR = Path(__file__).resolve().parent
CATEGORIES = ["Billing", "Technical", "Account", "Product"]
URGENCIES = ["Low", "Medium", "High"]
RANDOM_SEED = 42
DATA_NOTICE = (
    "The bundled tickets.csv contains synthetic development and demonstration "
    "examples, not real historical customer tickets. Results on synthetic data "
    "do not establish real-world accuracy."
)


def clean_ticket_text(ticket_text):
    """Normalize plain text; return empty text for missing/non-string entries."""
    if not isinstance(ticket_text, str):
        return ""
    text = html.unescape(ticket_text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def load_dataset(csv_path):
    """Validate labels and drop unusable rows before creating the split."""
    tickets = pd.read_csv(csv_path)
    required_columns = {"ticket_text", "category", "urgency", "resolution"}
    missing_columns = required_columns - set(tickets.columns)
    if missing_columns:
        raise ValueError(f"Missing dataset columns: {sorted(missing_columns)}")

    original_count = len(tickets)
    tickets["ticket_text"] = tickets["ticket_text"].map(clean_ticket_text)
    for column in ("category", "urgency", "resolution"):
        tickets[column] = tickets[column].map(
            lambda value: value.strip() if isinstance(value, str) else ""
        )
    valid_rows = (
        tickets["ticket_text"].str.contains(r"\w", regex=True)
        & tickets["category"].isin(CATEGORIES)
        & tickets["urgency"].isin(URGENCIES)
        & tickets["resolution"].ne("")
    )
    tickets = tickets.loc[valid_rows].copy()
    print(f"Dropped {original_count - len(tickets)} missing or invalid rows.")

    # Identical normalized text must not appear on both sides of the split.
    label_counts = tickets.groupby("ticket_text")[["category", "urgency"]].nunique()
    if label_counts.gt(1).any().any():
        raise ValueError("Identical ticket texts have conflicting labels; fix the CSV.")
    before_deduplication = len(tickets)
    tickets = tickets.drop_duplicates(subset="ticket_text").reset_index(drop=True)
    print(f"Removed {before_deduplication - len(tickets)} duplicate ticket texts.")

    # Joint stratification preserves both target distributions in the holdout.
    counts = tickets.groupby(["category", "urgency"]).size()
    if len(counts) != len(CATEGORIES) * len(URGENCIES) or (counts < 4).any():
        raise ValueError("Provide at least 4 unique valid tickets per category/urgency pair.")
    return tickets


def evaluate_classifier(classifier, features, expected, labels, name, output_dir):
    """Print class-wise scores and save a labeled confusion matrix."""
    predicted = classifier.predict(features)
    report = classification_report(
        expected, predicted, labels=labels, output_dict=True, zero_division=0
    )
    accuracy = accuracy_score(expected, predicted)
    matrix = confusion_matrix(expected, predicted, labels=labels)
    matrix_table = pd.DataFrame(matrix, index=labels, columns=labels)
    matrix_table.index.name = "actual / predicted"
    matrix_table.to_csv(output_dir / f"{name}_confusion_matrix.csv")

    print(f"\n{name.title()} accuracy: {accuracy:.4f}")
    print(classification_report(expected, predicted, labels=labels, zero_division=0))
    print("Confusion matrix (rows = actual; columns = predicted):")
    print(matrix_table.to_string())
    return {
        "accuracy": accuracy,
        "class_wise_and_averages": report,
        "confusion_matrix": matrix.tolist(),
        "label_order": labels,
    }


def train_models(csv_path=PROJECT_DIR / "data" / "tickets.csv",
                 output_dir=PROJECT_DIR / "models"):
    """Fit on the training partition and evaluate once on the held-out test set."""
    print(DATA_NOTICE)
    tickets = load_dataset(csv_path)
    joint_labels = tickets["category"] + "_" + tickets["urgency"]
    train_tickets, test_tickets = train_test_split(
        tickets, test_size=0.25, random_state=RANDOM_SEED, stratify=joint_labels
    )

    # Resolution is reference documentation only, never an input feature.
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), min_df=1, sublinear_tf=True, max_features=15000
    )
    train_features = vectorizer.fit_transform(train_tickets["ticket_text"])
    test_features = vectorizer.transform(test_tickets["ticket_text"])

    category_model = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    urgency_model = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    category_model.fit(train_features, train_tickets["category"])
    urgency_model.fit(train_features, train_tickets["urgency"])

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluation = {
        "data_notice": DATA_NOTICE,
        "random_seed": RANDOM_SEED,
        "training_rows": len(train_tickets),
        "test_rows": len(test_tickets),
        "category": evaluate_classifier(
            category_model, test_features, test_tickets["category"],
            CATEGORIES, "category", output_dir
        ),
        "urgency": evaluate_classifier(
            urgency_model, test_features, test_tickets["urgency"],
            URGENCIES, "urgency", output_dir
        ),
    }
    (output_dir / "evaluation.json").write_text(
        json.dumps(evaluation, indent=2), encoding="utf-8"
    )
    joblib.dump(vectorizer, output_dir / "tfidf_vectorizer.joblib")
    joblib.dump(category_model, output_dir / "category_model.joblib")
    joblib.dump(urgency_model, output_dir / "urgency_model.joblib")
    print(f"\nSaved models and evaluation to {output_dir.resolve()}")
    print(DATA_NOTICE)
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PROJECT_DIR / "data" / "tickets.csv")
    parser.add_argument("--models-dir", type=Path, default=PROJECT_DIR / "models")
    args = parser.parse_args()
    try:
        train_models(args.data, args.models_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Training failed: {error}\n")


if __name__ == "__main__":
    main()
