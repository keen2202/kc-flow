"""Shared API dependencies: database session, pagination, request context."""

from typing import Annotated, Any

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field

from src.services.auth import User, get_current_user


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """FastAPI dependency for pagination parameters."""
    return PaginationParams(page=page, page_size=page_size)


def paginate(items: list[Any], total: int, params: PaginationParams) -> dict[str, Any]:
    """Create a paginated response."""
    return {
        "items": items,
        "pagination": {
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
            "total_pages": (total + params.page_size - 1) // params.page_size,
        },
    }


def success_response(data: Any = None, message: str = "success") -> dict[str, Any]:
    """Create a unified success response."""
    return {
        "code": 0,
        "message": message,
        "data": data,
    }


def error_response(code: int, message: str, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Create a unified error response."""
    return {
        "code": code,
        "message": message,
        "data": None,
        "errors": errors or [],
    }


CurrentUser = Annotated[User, Depends(get_current_user)]
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
