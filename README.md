# AI Customer Support Ticket Triage

AI-assisted support operations console with a React + TypeScript frontend,
a FastAPI bridge, and an independent Streamlit fallback. The Python backend runs
in the Python 3.12 `ticket_ai` Conda environment. No paid AI API is used.

## React operations console

The primary interface lives in `frontend/`: ticket input and real model results,
confidence and review explanations, support-team handoff, a saved evaluation
dashboard, and an About & method page. No metrics, queue assignments, or prediction
results are hardcoded. Example chips supply clearly labeled input text only.

The React client calls the existing FastAPI routes. Input limits come from the
OpenAPI schema; health, prediction, and evaluation JSON is checked at runtime.
Confidence stays in its original 0–1 range until display. No ML source, data, or
artifacts are changed. The source is organized into `src/app`, `src/components/ui`,
`src/components/triage`, `src/components/performance`, `src/pages`, `src/lib`, and
`src/styles`. CSS Modules and design tokens provide both themes; Geist fonts are
bundled locally.

Only the theme preference uses browser storage. Ticket input/results remain in
React memory while navigating and disappear on reload. Tickets flagged by the API
for manual review are stored on the server in a private JSONL log. Submit synthetic
or non-sensitive demonstration tickets. There is no analytics, external service
call, or interactive approval system. Routing is a recommendation and does not
forward tickets to another service.

### Development on Windows

Requires Node.js 20.19+ or 22.12+ (validated with Node 24) and `ticket_ai`.
From the project folder, start the API in one terminal:

```powershell
conda activate ticket_ai
python -m uvicorn api.main:app --reload --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://localhost:8000`.
Use Ctrl+C to stop each process. If Conda is not on PATH, use the explicit
interpreter commands documented below.

### Production build and single-service run

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
Set-Location ..
conda activate ticket_ai
python -m uvicorn api.main:app --port 8000
```

Open `http://127.0.0.1:8000`. Start/restart FastAPI after `frontend/dist` exists.
The backend serves built assets and frontend routes while preserving `/api`.
Node is needed for development/build, not for serving the production build.
The threshold is developer-controlled through `REVIEW_THRESHOLD` or `api/config.py`;
there is no frontend threshold control.

The legacy fallback remains independently runnable:

```powershell
conda activate ticket_ai
python -m streamlit run app.py
```

### Frontend verification

`typecheck`, `lint`, and `build` are real checks. ESLint and TypeScript ESLint are
development-only dependencies. No UI toolkit, CSS framework, or chart library is used.
After building, run from the project folder using `ticket_ai`:

```powershell
python -B -m pytest tests/test_api_parity.py -q
python -B tests/validate_frontend.py
```

The integration script starts temporary API processes and stops them in cleanup.
It checks the built frontend, assets, SPA/API isolation, real client predictions
against direct ML and Streamlit AppTest for billing, technical, and vague inputs,
and actual React component rendering for every KPI, class-table score/support,
and confusion-matrix cell. It checks semantic text contrast in both themes, stops
the API for the unreachable case, and restarts with a nonexistent `EVALUATION_PATH`.
It does not rename or edit protected files. These component/server checks do not
replace browser layout and interaction checks.

Manual checklist when no connected browser is available:

- Inspect 375, 768, 1024, and 1440px in both themes. Confirm no horizontal page
  scroll, readable labels, contained table scrolling, and sidebar/rail/bottom navigation.
- Use only the keyboard: skip link, ticket input, Ctrl/Cmd+Enter, result heading,
  classifier tabs, matrix modes, and matrix cell arrow navigation. Check visible focus.
- Try the billing, technical, and vague example inputs; inspect loading skeletons,
  confidence ticks, review reasons, suggested handoff, and copy-summary feedback.
- Navigate away and back: text/results should remain. Edit/clear the ticket: the
  old result should disappear. Reload: text/results should clear.
- Compare both classifiers with the saved evaluation and download the original JSON.
  Hover/focus matrix cells and test both count and percentage display modes.
- Stop the API while Vite stays running; check actionable errors, preserved input,
  and retry. Restart with an invalid `EVALUATION_PATH` to inspect the missing-file
  screen, then restore the environment setting.
- Toggle theme and reload. Check reduced motion and Clipboard access denied.

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
| `GET /api/review-log` | Administrator-only paginated manual-review records |

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

CORS permits only `http://localhost:5173` and `http://127.0.0.1:5173`. If
`frontend/dist` folder exists when the API starts, static assets are served at `/`
and frontend page routes fall back to `index.html`. Unknown `/api` routes and
missing assets with file extensions return 404 instead of the frontend. The backend
also starts without that folder. The React frontend is in `frontend/`. Manual-review
records are exposed only by the authenticated review-log endpoint, never as static files.

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

Public triage has no authentication or rate limiting. Review records require an
administrator token as described below. Before external deployment, add production
authentication, request limits, HTTPS, and an explicit customer-data policy. CORS
alone is not authentication. API error handlers do not print customer text or tokens.

## Manual-review records and administrator access

Only genuine `POST /api/triage` predictions with `needs_review: true` create a record.
Confident automatic routes are not logged. Each record has a UUID ticket ID, UTC
timestamp, original submitted text, actual predicted category and urgency with their
confidence values, review reasons, suggested support queue, and `pending` status.
The prediction response shape, probabilities, and developer-controlled threshold
are preserved. The Streamlit fallback continues to use its original prediction
path; it does not create API review records.

The default file is `logs/manual_review.jsonl`; the directory is ignored by Git.
`REVIEW_LOG_PATH` can point to a different private location. Relative paths resolve
against this project. Keep credentials and ticket files out of source control,
frontend assets, and public directories. `.env` files are ignored, but this project
does not automatically load them: set server environment variables explicitly.

Before starting the API, set a strong administrator token without putting it in
shell history or frontend source:

```powershell
$reviewSecret = Read-Host 'Administrator review token' -AsSecureString
$env:ADMIN_REVIEW_TOKEN = [System.Net.NetworkCredential]::new('', $reviewSecret).Password
$env:REVIEW_LOG_PATH = 'logs/manual_review.jsonl'
$env:REVIEW_LOG_PAGE_SIZE = '20'
& "$env:USERPROFILE\anaconda3\envs\ticket_ai\python.exe" -m uvicorn api.main:app --port 8000
```

Open **Manual Review Log** in the React navigation and enter the same token there.
It is sent only in `Authorization: Bearer <token>`, held in React memory, and cleared
when access is locked or the page is left. Do not prefix the environment variable
with `VITE_`, put it in a URL, or store it in browser storage. Review responses use
`Cache-Control: no-store`. Public health, evaluation, and triage still work without
administrator credentials.

`GET /api/review-log?page=1&page_size=20` returns `items`, `page`, `page_size`, `total`,
and `total_pages`, with newest records first. Page size defaults to the server
setting and is limited to 100. Missing files and empty logs return an empty list.
The table and detail panel show actual stored records; no records are seeded.
There are no approve, assign, or status-changing controls in this phase.

- Missing or invalid credentials return 401 `UNAUTHORIZED`.
- An unset/blank server token disables reading with 503 `REVIEW_ACCESS_DISABLED`
  and a configuration instruction; it does not disable public classification.
- Unreadable storage returns 503 `REVIEW_LOG_UNAVAILABLE`; corrupted records return
  503 `REVIEW_LOG_CORRUPTED`. Internal paths and exception details are not exposed.
- If a flagged ticket cannot be stored, triage returns a clear storage error rather
  than reporting success while silently losing the review record. A retry is a new
  request and can produce a separate record.

Writers and readers coordinate with a thread lock and an OS file lock (Windows or
POSIX) on a separate lock file. Same-directory temporary files, flush/fsync, and
atomic replacement protect JSONL from partial/interleaved records. Existing corrupt
data is not silently discarded. This low-volume design rewrites the snapshot on
each append and reads the log for pagination; it is not intended for large queues.

**Local JSONL is not permanent cloud persistence.** Ephemeral deployment disks can
lose records on restart/redeploy, and separate instances do not share local files.
Use a private persistent volume if retention is required and verify filesystem lock
and rename support. The token is a demonstration-level shared secret, not production
authentication: there are no administrator identities, per-user audit trails, rate
limits, automatic retention/deletion, or encryption at rest. Restrict filesystem
permissions and use HTTPS before exposing customer data. Rotating the environment
token and restarting revokes old shared credentials.

The character limit remains **10–20,000 trimmed Unicode characters**, matching the
existing API rather than weakening its validation. React reads these limits from
OpenAPI for its counter and messages; supplementary Unicode characters count the
same way as Python. The threshold stays 0.60 unless server configuration overrides it.

Run all Python tests and the live integration harness without creating real review records:

```powershell
& "$env:USERPROFILE\anaconda3\envs\ticket_ai\python.exe" -B -m pytest tests -q
& "$env:USERPROFILE\anaconda3\envs\ticket_ai\python.exe" -B tests/validate_frontend.py
```

Tests use temporary review paths and temporary credentials. The integration harness
also sets a temporary log path before starting any API process. No real review log
or administrator credential is committed or generated during project validation.

### Readability and responsive checks

The existing Geist typography and palette are preserved. Body text, navigation,
labels, buttons, and supporting prediction details now use a clearer hierarchy;
small captions are increased without making every element the same size. Controls
retain mobile-friendly touch targets. The review log adds a fourth navigation item,
with shorter labels in the mobile bottom bar.

The top-right tooltip previously projected its maximum-content width past the
viewport, including while hidden. Tooltips now anchor inward, and targeted grid/flex
shrink constraints prevent content from forcing page tracks wider. Evaluation and
review tables retain their own keyboard-focusable horizontal scroll containers;
horizontal overflow is not globally hidden.

No browser connection is available in this session, so automated component/server
checks do not establish the rendered layouts at 1440, 1024, 768, or 375px. At each
width, check both themes, tooltip placement, navigation, ticket/prediction cards,
table scrolling, token entry/lock, pagination, detail-panel focus, and readable text.
The manual checklist above remains applicable. No deployment was performed.

Latest executed checks: **102 Python tests passed**, **18 live frontend/client and
React-rendering checks passed**, and TypeScript, ESLint, and the production build
passed. The live run verified protected review access, real records, both saved
evaluations, Unicode input boundaries, and the Streamlit prediction fallback.
Its Vite-proxy subcheck was skipped because port 8000 was already occupied; the
temporary validation API used another port. All validation-owned servers stopped.
Browser screenshots and rendered viewport checks remain manual as noted above.

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
