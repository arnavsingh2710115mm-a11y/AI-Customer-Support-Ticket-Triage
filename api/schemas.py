"""Validation and public response structures for the HTTP API."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from api.config import MAX_TEXT_LENGTH, MIN_TEXT_LENGTH


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Category = Literal["Billing", "Technical", "Account", "Product"]
Urgency = Literal["Low", "Medium", "High"]
SupportQueue = Literal["Billing Support", "Technical Support", "Account Support", "Product Support"]


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(strict=True, min_length=MIN_TEXT_LENGTH, max_length=MAX_TEXT_LENGTH)

    @field_validator("text", mode="before")
    @classmethod
    def strip_surrounding_whitespace(cls, value):
        return value.strip() if isinstance(value, str) else value


class CategoryResult(BaseModel):
    label: Category
    confidence: Probability
    probabilities: dict[Category, Probability]


class UrgencyResult(BaseModel):
    label: Urgency
    confidence: Probability
    probabilities: dict[Urgency, Probability]


class RoutingDecision(BaseModel):
    needs_review: bool
    reasons: list[str]
    assigned_queue: SupportQueue | None
    suggested_queue: SupportQueue


class TriageResponse(BaseModel):
    category: CategoryResult
    urgency: UrgencyResult
    decision: RoutingDecision
    review_threshold: Probability


class ModelAvailability(BaseModel):
    category: bool
    urgency: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    models_loaded: bool
    review_threshold: Probability
    models: ModelAvailability


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class EvaluationResponse(RootModel[dict[str, Any]]):
    """Keep the original evaluation keys and values, including future metadata."""
