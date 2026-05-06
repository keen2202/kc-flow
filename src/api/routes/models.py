"""Model management API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, success_response
from src.services.model_router import ModelConfig, ModelProvider, ModelRouter

router = APIRouter(prefix="/models", tags=["Models"])

# Module-level singleton — initialised lazily on first request.
_router: ModelRouter | None = None


def _get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


# ── Request / Response Schemas ──────────────────────────


class ModelOut(BaseModel):
    model_id: str
    provider: str
    display_name: str
    context_window: int
    supports_vision: bool
    supports_streaming: bool
    input_price_per_1k: float
    output_price_per_1k: float


class RegisterModelRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(..., pattern="^(openai|anthropic|local)$")
    display_name: str = ""
    context_window: int = 128000
    supports_vision: bool = False
    supports_streaming: bool = True
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0


class UpdateCredentialsRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    base_url: str | None = None


# ── Endpoints ───────────────────────────────────────────


@router.get("")
async def list_models() -> dict[str, Any]:
    """List all registered model configurations."""
    router = _get_router()
    models = [
        ModelOut(
            model_id=cfg.model_id,
            provider=cfg.provider.value,
            display_name=cfg.display_name,
            context_window=cfg.context_window,
            supports_vision=cfg.supports_vision,
            supports_streaming=cfg.supports_streaming,
            input_price_per_1k=cfg.input_price_per_1k,
            output_price_per_1k=cfg.output_price_per_1k,
        ).model_dump()
        for cfg in router._models.values()
    ]
    return success_response(models)


@router.post("")
async def register_model(request: RegisterModelRequest, current_user: CurrentUser) -> dict[str, Any]:
    """Register a custom model configuration."""
    router = _get_router()
    config = ModelConfig(
        model_id=request.model_id,
        provider=ModelProvider(request.provider),
        display_name=request.display_name or request.model_id,
        context_window=request.context_window,
        supports_vision=request.supports_vision,
        supports_streaming=request.supports_streaming,
        input_price_per_1k=request.input_price_per_1k,
        output_price_per_1k=request.output_price_per_1k,
    )
    router.register_model(config)
    return success_response({"model_id": config.model_id, "registered": True})


@router.put("/{model_id}/credentials")
async def update_credentials(
    model_id: str,
    request: UpdateCredentialsRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update API credentials for a model provider."""
    router = _get_router()
    config = router.get_model_config(model_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    provider = router._providers.get(config.provider)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Provider '{config.provider.value}' not initialised")

    provider.api_key = request.api_key
    if request.base_url:
        provider.base_url = request.base_url

    return success_response({"model_id": model_id, "credentials_updated": True})


@router.delete("/{model_id}/credentials")
async def delete_credentials(
    model_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Remove a model registration."""
    router = _get_router()
    if model_id not in router._models:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    del router._models[model_id]
    return success_response({"model_id": model_id, "deleted": True})
