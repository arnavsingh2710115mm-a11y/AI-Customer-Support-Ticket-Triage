# AI Customer Support Ticket Triage

Beginner-friendly machine-learning backend and Streamlit dashboard for Python 3.12
in the `ticket_ai` Conda environment. No paid AI API is used.

## Dataset provenance

**Every row in `data/tickets.csv` is synthetic**, written for development and
demonstration. These are not real historical customer tickets. There are 216
distinct examples: 54 per category and 72 per urgency, with 18 examples for
each category/urgency combination. Resolutions describe suggested handling,
not verified customer outcomes. They are never used as model inputs or targets.

Urgency labels reflect the scenario: Low generally means informational requests
without active disruption; Medium means a problem with a workaround or limited
impact; High means immediate material impact, security risk, or a critical deadline.
These demonstration labels need review against an actual support team's policy.

## Implementation

- `train_model.py` cleans text, drops missing/invalid rows, checks conflicting
  labels, removes identical normalized tickets, and splits data 75/25 using seed 42.
  Joint category/urgency stratification keeps all combinations represented.
- TF-IDF learns its vocabulary only from training text. Two Logistic Regression
  models predict category and urgency independently.
- Training prints accuracy and class-wise precision, recall, F1, and support,
  including macro/weighted averages. It saves the same results in
  `models/evaluation.json`, plus labeled confusion matrices as CSV files
  (rows are actual labels, columns are predicted labels).
- `predict_ticket.py` shares the same text cleaning and returns model probability
  scores for both predictions, per-class probabilities, and a support queue.
  Either score below the threshold sends the ticket to `Manual Review`, while
  preserving its suggested category queue. Unrecognized vocabulary also triggers
  review. The default threshold is 0.60; use `--threshold` or the function argument
  to change it.

## Run the dashboard

The dashboard uses the existing trained artifacts; it never retrains on a rerun.
When ready, install the updated dependencies and launch it manually:

```powershell
conda activate ticket_ai
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

`app.py` provides ticket input, category/urgency result cards, probability indicators,
support queue routing, and manual review warnings. The sidebar controls the review
threshold. Changing ticket text or the threshold clears the previous decision until
the ticket is classified again. The performance tab reads actual saved evaluation
results, with macro and weighted metrics, class-wise scores, and annotated confusion
matrices. `styles.css` and `.streamlit/config.toml` provide the light blue theme.

For deployment, include `app.py`, `styles.css`, `.streamlit/config.toml`, both backend
Python files, `requirements.txt`, and these trusted artifacts in `models/`:

- `tfidf_vectorizer.joblib`
- `category_model.joblib`
- `urgency_model.joblib`
- `evaluation.json` (needed for the performance tab)

Use Python 3.12 and the same scikit-learn version used to create the model files;
record/pin your training environment's versions before deployment. Paths resolve
relative to the source files. Models are cached with `st.cache_resource` and the
evaluation with `st.cache_data`; file modification timestamps and sizes invalidate
the caches when artifacts change. Missing artifacts produce setup guidance instead
of automatic training. A missing evaluation file does not disable prediction.

Packages were not installed and the dashboard was not launched during implementation.

## Backend commands

The environment must already exist. The saved models can be reused directly.
To intentionally train again or use command-line prediction, run manually:

```powershell
conda activate ticket_ai
python -m pip install -r requirements.txt
python train_model.py
python predict_ticket.py "Our production integration is down and all orders are failing." --threshold 0.65
```

From Python, call `predict_ticket(text, confidence_threshold=0.65)` from the
`predict_ticket` module after training. Input must be a nonempty string. Dataset
and model paths default to this project directory, regardless of the shell's
working directory. CLI overrides are available via `--data` and `--models-dir`.
Training creates the `models` folder and saves the vectorizer and two classifiers
using Joblib. Only load artifacts from trusted sources.

**Synthetic evaluation does not establish real-world accuracy.** Similar wording
and artificial class balance can make a synthetic holdout easier than real tickets.
Before production use, collect independently labeled real tickets, assess class-wise
performance and confidence calibration, and choose a review threshold based on
support costs. Probability scores are not guarantees of correctness.
