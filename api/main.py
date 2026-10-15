"""FastAPI bridge. Run: python -m uvicorn api.main:app --port 8000."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from api import config, service
from api.schemas import (
    ErrorResponse, EvaluationResponse, HealthResponse, TriageRequest, TriageResponse,
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
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request, error):
        # FastAPI's default response echoes rejected input; do not echo tickets.
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
        }})

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
        return service.triage_ticket(ticket.text, models)

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
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
    return application


app = create_app()
