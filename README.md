# AI Customer Support Ticket Triage

Beginner-friendly machine-learning backend, FastAPI bridge, and Streamlit fallback
for Python 3.12 in the `ticket_ai` Conda environment. No paid AI API is used.

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
support queue routing, and manual review warnings. The review threshold is controlled
by the server configuration in `api/config.py`. Changing ticket text clears the previous decision until
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

The Streamlit fallback runs independently of the FastAPI server.

## FastAPI backend

The API is a bridge to the existing prediction functions. It loads the trusted
vectorizer and both classifiers once per server process at startup. It does not
train models or modify data, evaluation results, or saved artifacts.

From this project folder, use the existing Python 3.12 `ticket_ai` environment:

```powershell
conda activate ticket_ai
python -m pip install -r requirements-dev.txt
python -m uvicorn api.main:app --reload --port 8000
```

If Conda is not on PATH, the equivalent commands on this machine are:

```powershell
& "$env:USERPROFILE\anaconda3\envs\ticket_ai\python.exe" -m uvicorn api.main:app --reload --port 8000
& "$env:USERPROFILE\anaconda3\envs\ticket_ai\python.exe" -B -m pytest tests/test_api_parity.py -q
```

API documentation is at `http://127.0.0.1:8000/api/docs`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Model readiness and read-only review threshold; 503 if loading failed |
| `POST /api/triage` | Classify and route through the original trained models |
| `GET /api/evaluation` | Original saved evaluation values, without recomputation |
| `GET /api/evaluation/download` | Download the original evaluation bytes |

Example request using PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
$ticketBody = @{ text = 'My payment was deducted twice.' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/triage -Method Post -ContentType 'application/json' -Body $ticketBody
```

The triage response contains `category` and `urgency` objects with `label`, raw
`confidence`, and full `probabilities`. The `decision` object contains `needs_review`,
`reasons`, `assigned_queue`, and `suggested_queue`. When review is required,
`assigned_queue` is null and the suggested category queue remains available. The
API reports a routing decision; it does not send a ticket to an external service.
The read-only `review_threshold` is also returned.

Only the `text` field is accepted. Text is strictly a string, trimmed, and must
contain 10–20,000 characters. The maximum preserves the existing Streamlit limit;
10 is the API minimum because the fallback had no explicit minimum. Empty,
formatting-only, invalid-type, and extra-field requests receive HTTP 422. Clients
cannot override the threshold. Errors use `{"error": {"code": "...", "message": "..."}}`
and do not echo ticket text, local paths, or internal exceptions.

Server administrators may set configuration before starting either application:

```powershell
$env:REVIEW_THRESHOLD = '0.60'
$env:EVALUATION_PATH = 'models/evaluation.json'
```

The threshold must be finite and between 0 and 1 inclusive; invalid configuration
fails startup with a concise message. Relative evaluation paths resolve against the
project folder; absolute paths are supported. Restart the processes after changes.
The Streamlit threshold slider has been removed; its tabs and evaluation remain.
The independent legacy prediction CLI retains its existing threshold argument.

Missing/unreadable models produce 503 `MODELS_MISSING` on health and triage; provide
all three trusted artifacts from the same run with compatible dependencies and
restart. Evaluation remains accessible if models fail to load. A missing evaluation
returns 404 `EVALUATION_MISSING`; unreadable or malformed JSON has a structured 503.
Models do not automatically reload while the server runs.

CORS permits only `http://localhost:5173` and `http://127.0.0.1:5173`. If a future
`frontend/dist` folder exists when the API starts, static assets are served at `/`
and frontend page routes fall back to `index.html`. Unknown `/api` routes and
missing assets with file extensions return 404 instead of the frontend. The backend
also starts without that folder. No React frontend or review logging is included.

Run the meaningful automated checks with the environment's interpreter:

```powershell
python -B -m pytest tests/test_api_parity.py -q
```

Tests compare genuine direct/API predictions on the first three tickets per
category, exercise threshold routing, strict validation, unchanged evaluation and
downloads, missing artifacts, model caching, CORS, SPA routing, configuration, and
the Streamlit fallback via AppTest. Temporary fixtures never alter real artifacts.
The suite also verifies that protected ML sources, data, and model files retain
their original SHA-256 hashes throughout testing.

The added dependencies were validated in `ticket_ai` with FastAPI 0.143.1,
Uvicorn 0.54.0, pytest 9.1.1, httpx 0.28.1, and Pydantic 2.14.1. The existing
scikit-learn version is 1.9.1. The four newly declared API/test dependencies are
pinned to their installed versions after validation. Starlette currently emits a
non-failing deprecation warning about its httpx TestClient adapter; the requested
httpx dependency remains in use without adding another HTTP client.

This development API has no authentication, rate limiting, or persistent ticket
storage. Before external deployment, add access controls, request limits, HTTPS,
and an explicit policy for handling customer data. CORS alone is not authentication.
No customer text is intentionally logged by the API's error handlers.

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
