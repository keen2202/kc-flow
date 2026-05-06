"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import get_settings
from src.core.exceptions import WorkflowError
from src.core.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting workflow engine", environment=settings.environment)

    # TODO: initialize database pool, redis, etc.

    yield

    # Shutdown
    logger.info("Shutting down workflow engine")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AI Workflow Orchestration Engine",
        description="Visual workflow designer with AI node orchestration",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # ── Middleware ──
    from src.api.middleware import RequestIDMiddleware, LoggingMiddleware, RateLimitMiddleware

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ──
    @app.exception_handler(WorkflowError)
    async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:
        status_map = {
            "unauthorized": 401,
            "access_denied": 403,
            "workflow_not_found": 404,
            "execution_not_found": 404,
            "node_type_not_found": 404,
            "skill_not_found": 404,
            "circuit_breaker_open": 503,
        }
        status_code = status_map.get(exc.code, 400 if "validation" in exc.code or "parse" in exc.code else 500)
        return JSONResponse(
            status_code=status_code,
            content={
                "code": status_code * 100 + 1,
                "message": exc.message,
                "data": None,
                "errors": [{"field": k, "reason": v} for k, v in exc.details.items()] if exc.details else [],
            },
        )

    # ── Health Check ──
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # ── API Routes ──
    from src.api.routes import workflows, nodes, skills, auth, streaming, marketplace, models

    app.include_router(workflows.router, prefix=settings.api_prefix)
    app.include_router(nodes.router, prefix=settings.api_prefix)
    app.include_router(skills.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(streaming.router, prefix=settings.api_prefix)
    app.include_router(marketplace.router, prefix=settings.api_prefix)
    app.include_router(models.router, prefix=settings.api_prefix)

    return app


app = create_app()
