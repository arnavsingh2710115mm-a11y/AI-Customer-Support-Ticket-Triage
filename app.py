"""Streamlit dashboard for the existing trained ticket triage backend."""

import html
import json
import logging

import pandas as pd
import streamlit as st

from predict_ticket import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    MODEL_FILENAMES,
    PROJECT_DIR,
    load_ticket_models,
    predict_ticket,
)


MODELS_DIR = PROJECT_DIR / "models"
EVALUATION_PATH = MODELS_DIR / "evaluation.json"
LOGGER = logging.getLogger(__name__)


def file_signature(paths):
    """Invalidate cached resources if their saved files are replaced."""
    return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)


@st.cache_resource(show_spinner=False)
def cached_models(signature):
    """Share read-only fitted models across reruns without training anything."""
    return load_ticket_models(MODELS_DIR)


@st.cache_data(show_spinner=False)
def cached_evaluation(signature):
    """Read actual training output; never substitute example scores."""
    return json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))


def show_prediction(result):
    st.subheader("Triage result")
    category_column, urgency_column = st.columns(2)
    for column, title, label, confidence in (
        (category_column, "Category", result["category"], result["category_confidence"]),
        (urgency_column, "Urgency", result["urgency"], result["urgency_confidence"]),
    ):
        with column, st.container(border=True):
            st.metric(title, label)
            st.progress(confidence, text=f"Confidence: {confidence:.1%}")

    with st.container(border=True):
        st.markdown("**Assigned support queue**")
        st.subheader(result["queue"])
        if result["needs_manual_review"]:
            st.warning("Manual review required. Review this ticket before forwarding it.")
            st.write(f"Suggested team after review: {result['suggested_queue']}")
            for reason in result["review_reasons"]:
                st.write(f"• {reason}")
        else:
            st.success("Manual review is not required by the current confidence rule.")
        st.caption(f"Review threshold used: {result['confidence_threshold']:.0%}")

    with st.expander("All class confidence scores"):
        left, right = st.columns(2)
        for column, title, key in (
            (left, "Category", "category_probabilities"),
            (right, "Urgency", "urgency_probabilities"),
        ):
            with column:
                st.markdown(f"**{title}**")
                scores = pd.DataFrame(
                    result[key].items(), columns=["Class", "Probability"]
                ).set_index("Class")
                st.dataframe(scores.style.format("{:.1%}"), use_container_width=True)
    st.caption("Confidence scores are model probabilities, not guarantees of correctness.")


def show_ticket_interface():
    st.subheader("Classify a support ticket")
    st.write("Describe the customer's issue to predict its category, urgency, and support queue.")
    signature = None
    try:
        signature = file_signature([MODELS_DIR / name for name in MODEL_FILENAMES])
    except OSError:
        st.error("The trained model files are missing or cannot be read.")
        st.info(
            "Place tfidf_vectorizer.joblib, category_model.joblib, and urgency_model.joblib "
            "in this project's models/ folder. If models have not been trained, run "
            "`python train_model.py` manually in the ticket_ai environment first. "
            "The dashboard never trains models automatically."
        )

    ticket_text = st.text_area(
        "Customer support ticket", height=180, max_chars=20000,
        placeholder="Describe what happened, who is affected, and any deadlines…",
        help="Enter the ticket itself. Avoid including passwords or payment card details.",
    )
    threshold = st.sidebar.slider(
        "Manual review threshold", min_value=0.0, max_value=1.0,
        value=DEFAULT_CONFIDENCE_THRESHOLD, step=0.05, format="%.2f",
        help="Review is required if either prediction score is below this value. "
             "Text with no recognized vocabulary always requires review.",
    )
    st.sidebar.caption("Higher thresholds send more tickets for human review.")
    current_input = (ticket_text, threshold, signature)
    # Do not leave an old routing decision visible after input/settings change.
    if st.session_state.get("prediction_input") != current_input:
        st.session_state.pop("prediction_result", None)

    submitted = st.button("Classify ticket", type="primary", disabled=signature is None)
    if submitted:
        st.session_state.pop("prediction_result", None)
        if not ticket_text.strip():
            st.warning("Enter customer support ticket text before classifying.")
        else:
            try:
                with st.spinner("Classifying ticket…"):
                    result = predict_ticket(
                        ticket_text, confidence_threshold=threshold,
                        loaded_models=cached_models(signature),
                    )
                st.session_state["prediction_input"] = current_input
                st.session_state["prediction_result"] = result
            except ValueError as error:
                st.error(f"Unable to classify this ticket: {error}")
            except Exception:
                LOGGER.exception("Ticket prediction failed")
                st.error(
                    "Prediction could not be completed. Check that all three model files "
                    "come from the same training run and that the deployment uses the "
                    "same scikit-learn version as training. See server logs for details."
                )

    if "prediction_result" in st.session_state:
        show_prediction(st.session_state["prediction_result"])


def show_confusion_matrix(matrix, labels, title):
    """Render a small annotated heatmap without another plotting dependency."""
    largest = max(max(row) for row in matrix) or 1
    header = "".join(f'<th scope="col">{html.escape(str(label))}</th>' for label in labels)
    rows = []
    for label, row in zip(labels, matrix):
        cells = "".join(
            f'<td style="background:rgba(37,99,235,{0.05 + 0.3 * value / largest:.3f})">'
            f'{int(value)}</td>' for value in row
        )
        rows.append(f'<tr><th scope="row">{html.escape(str(label))}</th>{cells}</tr>')
    st.markdown(
        '<div class="matrix-scroll"><table class="confusion-matrix">'
        f'<caption>{html.escape(title)} — rows: actual; columns: predicted</caption>'
        f'<thead><tr><th scope="col">Actual / predicted</th>{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True,
    )


def show_classifier_evaluation(name, evaluation):
    labels = evaluation["label_order"]
    report = evaluation["class_wise_and_averages"]
    average = report["macro avg"]
    columns = st.columns(4)
    for column, label, value in zip(
        columns, ["Accuracy", "Precision · macro", "Recall · macro", "F1 · macro"],
        [evaluation["accuracy"], average["precision"], average["recall"], average["f1-score"]],
    ):
        column.metric(label, f"{value:.2%}")
    st.caption("Macro averages give each class equal weight. Weighted averages appear below.")
    st.markdown("**Class-wise performance**")
    table = pd.DataFrame.from_dict(
        {label: report[label] for label in labels + ["macro avg", "weighted avg"]},
        orient="index",
    )[["precision", "recall", "f1-score", "support"]]
    table.index.name = "Class / average"
    st.dataframe(
        table.style.format({
            "precision": "{:.2%}", "recall": "{:.2%}",
            "f1-score": "{:.2%}", "support": "{:.0f}",
        }), use_container_width=True,
    )
    st.caption("Support is the number of held-out test tickets for each class.")
    st.markdown("**Confusion matrix**")
    show_confusion_matrix(evaluation["confusion_matrix"], labels, name)


def show_evaluation():
    st.subheader("Model performance")
    st.info(
        "These models were trained and evaluated using synthetic tickets. "
        "These results do not establish real-world accuracy."
    )
    try:
        evaluation = cached_evaluation(file_signature([EVALUATION_PATH]))
        st.caption(
            f"Saved evaluation · {evaluation['training_rows']} training tickets · "
            f"{evaluation['test_rows']} held-out test tickets · "
            f"Random seed {evaluation['random_seed']}"
        )
        category_tab, urgency_tab = st.tabs(["Category classifier", "Urgency classifier"])
        with category_tab:
            show_classifier_evaluation("Category", evaluation["category"])
        with urgency_tab:
            show_classifier_evaluation("Urgency", evaluation["urgency"])
        st.download_button(
            "Download saved evaluation", data=json.dumps(evaluation, indent=2),
            file_name="evaluation.json", mime="application/json",
        )
        st.caption("Source: models/evaluation.json from training; no metrics are estimated by this dashboard.")
    except OSError:
        st.warning(
            "Saved evaluation is unavailable. Include models/evaluation.json from the "
            "same training run when deploying. Ticket prediction can still work without it."
        )
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        LOGGER.exception("Saved evaluation could not be displayed")
        st.error(
            "The saved evaluation file is invalid or incomplete. Restore evaluation.json "
            "generated by train_model.py. No fallback metrics are shown."
        )


def main():
    st.set_page_config(page_title="AI Ticket Triage", page_icon="📨", layout="wide")
    stylesheet = PROJECT_DIR / "styles.css"
    if stylesheet.is_file():
        st.markdown(f"<style>{stylesheet.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    st.markdown('<div class="app-eyebrow">SUPPORT OPERATIONS · AI ASSISTED TRIAGE</div>', unsafe_allow_html=True)
    st.title("AI Customer Support Ticket Triage")
    st.write("Turn customer issues into clear support priorities and routing decisions.")
    st.caption("Student demonstration · Trained on synthetic data · Human review for uncertain predictions")
    st.sidebar.title("Triage settings")
    st.sidebar.caption("TF-IDF + Logistic Regression · Local trained models")
    ticket_tab, performance_tab = st.tabs(["Ticket triage", "Model performance"])
    with ticket_tab:
        with st.container(border=True):
            show_ticket_interface()
    with performance_tab:
        with st.container(border=True):
            show_evaluation()


if __name__ == "__main__":
    main()
