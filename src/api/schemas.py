"""Unified API response schemas."""

from datetime import datetime
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field
import uuid

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API success response."""
    code: int = 0
    message: str = "success"
    data: T | None = None
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorDetail(BaseModel):
    field: str
    reason: str
    detail: str = ""


class ErrorResponse(BaseModel):
    """Unified API error response."""
    code: int
    message: str
    errors: list[ErrorDetail] = []
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""
    items: list[T]
    pagination: PaginationInfo
