"""FastAPI bridge. Run: python -m uvicorn api.main:app --port 8000."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from api import config, review_log, service
from api.schemas import (
    ErrorResponse, EvaluationResponse, HealthResponse, ReviewLogResponse,
    TriageRequest, TriageResponse,
)


@asynccontextmanager
async def lifespan(app):
    app.state.models = service.load_models()
    yield
    app.state.models = None


def get_models(request: Request):
    models = getattr(request.app.state, "models", None)
    if models is None:
        raise service.models_missing_error()
    return models


def authorize_review_access(request: Request):
    """Demo administrator access; never put credentials in URLs or logs."""
    expected_token = config.ADMIN_REVIEW_TOKEN
    if not expected_token or not expected_token.strip():
        raise service.ServiceError(
            503, "REVIEW_ACCESS_DISABLED",
            "Administrator review access is disabled. Set ADMIN_REVIEW_TOKEN "
            "in the server environment and restart the API to enable it.",
        )
    authorization = request.headers.get("Authorization", "").split()
    provided_token = authorization[1] if len(authorization) == 2 else ""
    matches = secrets.compare_digest(
        provided_token.encode("utf-8"), expected_token.encode("utf-8"),
    )
    if len(authorization) != 2 or authorization[0].lower() != "bearer" or not matches:
        raise service.ServiceError(
            401, "UNAUTHORIZED",
            "Enter a valid administrator token to access the manual-review log.",
        )


class SPAStaticFiles(StaticFiles):
    """Serve built assets, with index fallback only for frontend page routes."""

    async def get_response(self, path, scope):
        # StaticFiles uses OS-specific separators, including backslashes on Windows.
        route_path = path.replace("\\", "/").lstrip("/")
        if route_path == "api" or route_path.startswith("api/"):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def create_app():
    application = FastAPI(
        title="AI Customer Support Ticket Triage",
        description="Bridge to existing classifiers trained on synthetic data.",
        lifespan=lifespan,
        docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    )

    @application.exception_handler(service.ServiceError)
    async def handle_service_error(request, error):
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
            headers={"WWW-Authenticate": "Bearer"} if error.code == "UNAUTHORIZED" else None,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request, error):
        # FastAPI's default response echoes rejected input; do not echo tickets.
        if request.url.path.rstrip("/") == "/api/review-log":
            return JSONResponse(status_code=422, content={"error": {
                "code": "VALIDATION_ERROR",
                "message": "Page must be an integer of at least 1. Page size must be "
                           f"an integer from 1 to {config.REVIEW_LOG_MAX_PAGE_SIZE}.",
            }})
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR",
            "message": f"Send only a text string of {config.MIN_TEXT_LENGTH} to "
                       f"{config.MAX_TEXT_LENGTH} characters after trimming whitespace. "
                       "Additional fields, including review thresholds, are not allowed.",
        }})

    @application.exception_handler(HTTPException)
    async def handle_http_error(request, error):
        return JSONResponse(status_code=error.status_code, content={"error": {
            "code": f"HTTP_{error.status_code}",
            "message": "Requested resource not found." if error.status_code == 404
                       else "The request could not be completed.",
        }}, headers=error.headers)

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request, error):
        service.LOGGER.error("API request failed (%s)", type(error).__name__)
        return JSONResponse(status_code=500, content={"error": {
            "code": "INTERNAL_ERROR", "message": "The request could not be completed. Contact the server administrator.",
        }}, headers={"Cache-Control": "no-store"}
            if request.url.path.rstrip("/") == "/api/review-log" else None)

    errors = {422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}

    @application.get("/api/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
    def health(models=Depends(get_models)):
        return {
            "status": "ok", "models_loaded": True,
            "review_threshold": config.REVIEW_THRESHOLD,
            "models": {"category": True, "urgency": True},
        }

    @application.post("/api/triage", response_model=TriageResponse, responses=errors)
    def triage(ticket: TriageRequest, models=Depends(get_models)):
        prediction = service.triage_ticket(ticket.text, models)
        if prediction["decision"]["needs_review"]:
            review_log.log_review_ticket(ticket.original_text, prediction)
        return prediction

    @application.get(
        "/api/review-log", response_model=ReviewLogResponse,
        responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                   503: {"model": ErrorResponse}},
        dependencies=[Depends(authorize_review_access)],
    )
    def review_records(
        page: int = Query(1, ge=1),
        page_size: int | None = Query(None, ge=1, le=config.REVIEW_LOG_MAX_PAGE_SIZE),
    ):
        return review_log.read_review_page(page, page_size or config.REVIEW_LOG_PAGE_SIZE)

    @application.get(
        "/api/evaluation", response_model=EvaluationResponse,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def evaluation():
        return service.read_evaluation()

    @application.get(
        "/api/evaluation/download", response_class=Response,
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def evaluation_download():
        return Response(
            content=service.read_evaluation_bytes(), media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="evaluation.json"'},
        )

    # Registered last: built assets and SPA routes cannot mask API endpoints.
    if config.FRONTEND_DIST.is_dir():
        application.mount("/", SPAStaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")

    # Restrict cross-origin browser access to the approved local frontend origins.
    application.add_middleware(
        CORSMiddleware, allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"],
    )

    @application.middleware("http")
    async def prevent_review_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.rstrip("/") == "/api/review-log":
            # Include authorization, validation, CORS, and storage failures.
            response.headers["Cache-Control"] = "no-store"
        return response

    return application


app = create_app()
