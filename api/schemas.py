"""Validation and public response structures for the HTTP API."""

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, RootModel, field_validator, model_validator

from api.config import MAX_TEXT_LENGTH, MIN_TEXT_LENGTH


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Category = Literal["Billing", "Technical", "Account", "Product"]
Urgency = Literal["Low", "Medium", "High"]
SupportQueue = Literal["Billing Support", "Technical Support", "Account Support", "Product Support"]


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(strict=True, min_length=MIN_TEXT_LENGTH, max_length=MAX_TEXT_LENGTH)
    _original_text: str = PrivateAttr()

    @model_validator(mode="wrap")
    @classmethod
    def preserve_original_text(cls, value, handler):
        # Validation still trims the prediction input. The private attribute is
        # neither an accepted request field nor part of the public API response.
        original = value.get("text") if isinstance(value, dict) else None
        ticket = handler(value)
        ticket._original_text = original if isinstance(original, str) else ticket.text
        return ticket

    @property
    def original_text(self):
        return self._original_text

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


class ReviewRecord(BaseModel):
    """Private administrator record, validated before writing and after reading."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: UUID
    timestamp: datetime
    ticket_text: str = Field(strict=True)
    category: Category
    category_confidence: Probability
    urgency: Urgency
    urgency_confidence: Probability
    reasons: list[str] = Field(min_length=1)
    suggested_queue: SupportQueue
    status: Literal["pending"]

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Review timestamps must be in UTC.")
        return value


class ReviewLogResponse(BaseModel):
    items: list[ReviewRecord]
    page: int
    page_size: int
    total: int
    total_pages: int
