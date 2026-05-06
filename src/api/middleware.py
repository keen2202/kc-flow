"""API middleware: request ID, logging, rate limiting."""

import time
import uuid
from collections import defaultdict
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique request ID to every request for tracing."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Bind request_id to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs request/response details with structlog."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.monotonic()

        logger.info(
            "request_started",
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query),
            client=request.client.host if request.client else None,
        )

        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, app: Any, requests_per_minute: int = 60) -> None:
        super().__init__(app)
        self._requests_per_minute = requests_per_minute
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self._windows[client_ip]

        # Clean old entries (older than 60 seconds)
        window[:] = [t for t in window if now - t < 60]

        if len(window) >= self._requests_per_minute:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"code": 429, "message": "Rate limit exceeded", "data": None},
            )

        window.append(now)
        return await call_next(request)
