"""Authentication API endpoints."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from src.api.dependencies import CurrentUser, success_response
from src.services.auth import get_auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request with email/password."""
    email: str
    password: str


class RefreshRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class CreateApiKeyRequest(BaseModel):
    """API key creation request."""
    name: str = "default"
    expires_in_days: int | None = None
    rate_limit: int | None = None


class LoginResponse(BaseModel):
    """Login response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login")
async def login(request: LoginRequest):
    """Authenticate and get JWT tokens.

    In production, validates credentials against the database.
    For development, accepts any credentials.
    """
    auth_service = get_auth_service()

    # TODO: validate credentials against DB
    # For now, create a mock user
    user_id = f"user_{request.email.split('@')[0]}"
    workspace_id = "ws_default"

    token_pair = auth_service.create_token_pair(
        user_id=user_id,
        email=request.email,
        workspace_id=workspace_id,
        roles=["user"],
    )

    return success_response({
        "access_token": token_pair.access_token,
        "refresh_token": token_pair.refresh_token,
        "token_type": token_pair.token_type,
        "expires_in": token_pair.expires_in,
    })


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """Refresh access token using refresh token."""
    auth_service = get_auth_service()

    token_pair = auth_service.refresh_access_token(request.refresh_token)
    if not token_pair:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return success_response({
        "access_token": token_pair.access_token,
        "refresh_token": token_pair.refresh_token,
        "token_type": token_pair.token_type,
        "expires_in": token_pair.expires_in,
    })


@router.post("/api-keys")
async def create_api_key(request: CreateApiKeyRequest, current_user: CurrentUser):
    """Create a new API key. The full key is returned only once."""
    auth_service = get_auth_service()

    full_key, info = auth_service.create_api_key(
        user_id=current_user.user_id,
        workspace_id=current_user.workspace_id,
        name=request.name,
        expires_in_days=request.expires_in_days,
        rate_limit=request.rate_limit,
    )

    return success_response({
        "key": full_key,
        "key_id": info.key_id,
        "key_prefix": info.key_prefix,
        "name": info.name,
        "created_at": info.created_at,
        "expires_at": info.expires_at,
    })


@router.get("/api-keys")
async def list_api_keys(current_user: CurrentUser):
    """List API keys for the current user (prefix only, no secrets)."""
    auth_service = get_auth_service()
    keys = auth_service.list_api_keys(current_user.user_id)

    return success_response([
        {
            "key_id": k.key_id,
            "key_prefix": k.key_prefix,
            "name": k.name,
            "created_at": k.created_at,
            "last_used_at": k.last_used_at,
            "expires_at": k.expires_at,
            "is_active": k.is_active,
        }
        for k in keys
    ])


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, current_user: CurrentUser):
    """Revoke an API key."""
    auth_service = get_auth_service()

    if not auth_service.revoke_api_key(key_id, current_user.user_id):
        raise HTTPException(status_code=404, detail="API key not found")

    return success_response({"key_id": key_id, "revoked": True})
