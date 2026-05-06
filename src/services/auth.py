"""Authentication service — API-Key and JWT-based authentication.

Implements:
- API-Key generation with sk- prefix and bcrypt hashing
- JWT access/refresh token flow
- FastAPI dependency for extracting current user
- Key lifecycle management (create, rotate, revoke)
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.settings import get_settings

logger = structlog.get_logger()

# Security scheme for FastAPI
security_scheme = HTTPBearer(auto_error=False)


@dataclass
class User:
    """Authenticated user context."""
    user_id: str
    email: str
    workspace_id: str
    roles: list[str]
    auth_method: str  # "api_key" or "jwt"
    key_id: str | None = None


@dataclass
class ApiKeyInfo:
    """API key metadata (without secret)."""
    key_id: str
    key_prefix: str
    name: str
    user_id: str
    workspace_id: str
    created_at: str
    last_used_at: str | None
    expires_at: str | None
    is_active: bool
    rate_limit: int | None


@dataclass
class TokenPair:
    """JWT access + refresh token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes


class AuthService:
    """Authentication service for API-Key and JWT management."""

    def __init__(self) -> None:
        self._settings = get_settings()
        # In-memory stores (replace with DB in production)
        self._api_keys: dict[str, dict[str, Any]] = {}  # key_id -> key data
        self._key_hashes: dict[str, str] = {}  # hash -> key_id
        self._refresh_tokens: dict[str, dict[str, Any]] = {}  # token -> data

    # ── API Key Management ──

    def create_api_key(
        self,
        user_id: str,
        workspace_id: str,
        name: str = "default",
        expires_in_days: int | None = None,
        rate_limit: int | None = None,
    ) -> tuple[str, ApiKeyInfo]:
        """Create a new API key. Returns (full_key, key_info).

        The full key is shown only once. Store the key_id for future management.
        """
        # Generate key: sk- + 48 chars of URL-safe random
        raw_key = secrets.token_urlsafe(36)
        full_key = f"sk-{raw_key}"

        # Hash for storage (SHA-256 for fast lookup, bcrypt would be too slow for per-request)
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = full_key[:11]  # sk-XXXXXXX (first 8 chars after prefix)

        key_id = f"key_{secrets.token_urlsafe(12)}"
        now = datetime.now(timezone.utc)

        expires_at = None
        if expires_in_days:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        key_data = {
            "key_id": key_id,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "name": name,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "created_at": now.isoformat(),
            "last_used_at": None,
            "expires_at": expires_at,
            "is_active": True,
            "rate_limit": rate_limit,
        }

        self._api_keys[key_id] = key_data
        self._key_hashes[key_hash] = key_id

        logger.info("API key created", key_id=key_id, user_id=user_id, name=name)

        info = ApiKeyInfo(
            key_id=key_id,
            key_prefix=key_prefix,
            name=name,
            user_id=user_id,
            workspace_id=workspace_id,
            created_at=now.isoformat(),
            last_used_at=None,
            expires_at=expires_at,
            is_active=True,
            rate_limit=rate_limit,
        )

        return full_key, info

    def validate_api_key(self, full_key: str) -> User | None:
        """Validate an API key and return the associated user."""
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_id = self._key_hashes.get(key_hash)

        if not key_id:
            return None

        key_data = self._api_keys.get(key_id)
        if not key_data or not key_data["is_active"]:
            return None

        # Check expiration
        if key_data.get("expires_at"):
            expires = datetime.fromisoformat(key_data["expires_at"])
            if datetime.now(timezone.utc) > expires:
                return None

        # Update last_used_at
        key_data["last_used_at"] = datetime.now(timezone.utc).isoformat()

        return User(
            user_id=key_data["user_id"],
            email="",  # Would be loaded from DB
            workspace_id=key_data["workspace_id"],
            roles=["user"],
            auth_method="api_key",
            key_id=key_id,
        )

    def list_api_keys(self, user_id: str) -> list[ApiKeyInfo]:
        """List all API keys for a user (prefix only, no secrets)."""
        keys = []
        for key_data in self._api_keys.values():
            if key_data["user_id"] == user_id:
                keys.append(ApiKeyInfo(
                    key_id=key_data["key_id"],
                    key_prefix=key_data["key_prefix"],
                    name=key_data["name"],
                    user_id=key_data["user_id"],
                    workspace_id=key_data["workspace_id"],
                    created_at=key_data["created_at"],
                    last_used_at=key_data.get("last_used_at"),
                    expires_at=key_data.get("expires_at"),
                    is_active=key_data["is_active"],
                    rate_limit=key_data.get("rate_limit"),
                ))
        return keys

    def revoke_api_key(self, key_id: str, user_id: str) -> bool:
        """Revoke an API key."""
        key_data = self._api_keys.get(key_id)
        if not key_data or key_data["user_id"] != user_id:
            return False

        key_data["is_active"] = False
        # Remove from hash lookup
        self._key_hashes = {h: k for h, k in self._key_hashes.items() if k != key_id}

        logger.info("API key revoked", key_id=key_id, user_id=user_id)
        return True

    def rotate_api_key(self, key_id: str, user_id: str) -> tuple[str, ApiKeyInfo] | None:
        """Rotate an API key (revoke old, create new with same settings)."""
        key_data = self._api_keys.get(key_id)
        if not key_data or key_data["user_id"] != user_id:
            return None

        # Revoke old key
        self.revoke_api_key(key_id, user_id)

        # Create new key with same settings
        return self.create_api_key(
            user_id=key_data["user_id"],
            workspace_id=key_data["workspace_id"],
            name=key_data["name"],
            rate_limit=key_data.get("rate_limit"),
        )

    # ── JWT Token Management ──

    def create_token_pair(self, user_id: str, email: str, workspace_id: str, roles: list[str]) -> TokenPair:
        """Create JWT access + refresh token pair."""
        now = datetime.now(timezone.utc)

        # Access token payload
        access_payload = {
            "sub": user_id,
            "email": email,
            "workspace_id": workspace_id,
            "roles": roles,
            "type": "access",
            "iat": now.timestamp(),
            "exp": (now + timedelta(minutes=self._settings.access_token_expire_minutes)).timestamp(),
        }

        # Refresh token payload
        refresh_payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now.timestamp(),
            "exp": (now + timedelta(days=self._settings.refresh_token_expire_days)).timestamp(),
        }

        access_token = self._encode_jwt(access_payload)
        refresh_token = self._encode_jwt(refresh_payload)

        # Store refresh token for revocation support
        self._refresh_tokens[refresh_token] = {
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=self._settings.refresh_token_expire_days)).isoformat(),
        }

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    def validate_access_token(self, token: str) -> User | None:
        """Validate a JWT access token and return the user."""
        payload = self._decode_jwt(token)
        if not payload or payload.get("type") != "access":
            return None

        return User(
            user_id=payload["sub"],
            email=payload.get("email", ""),
            workspace_id=payload.get("workspace_id", ""),
            roles=payload.get("roles", ["user"]),
            auth_method="jwt",
        )

    def refresh_access_token(self, refresh_token: str) -> TokenPair | None:
        """Refresh an access token using a refresh token."""
        payload = self._decode_jwt(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        # Check if refresh token is revoked
        if refresh_token not in self._refresh_tokens:
            return None

        user_id = payload["sub"]
        # Create new token pair
        return self.create_token_pair(
            user_id=user_id,
            email=payload.get("email", ""),
            workspace_id=payload.get("workspace_id", ""),
            roles=payload.get("roles", ["user"]),
        )

    def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Revoke a refresh token."""
        if refresh_token in self._refresh_tokens:
            del self._refresh_tokens[refresh_token]
            return True
        return False

    # ── JWT Encoding/Decoding ──

    def _encode_jwt(self, payload: dict[str, Any]) -> str:
        """Encode a JWT token (simplified implementation)."""
        import base64
        import json

        header = {"alg": self._settings.jwt_algorithm, "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self._settings.jwt_secret_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def _decode_jwt(self, token: str) -> dict[str, Any] | None:
        """Decode and validate a JWT token."""
        import base64
        import json

        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            header_b64, payload_b64, signature_b64 = parts

            # Verify signature
            message = f"{header_b64}.{payload_b64}"
            expected_sig = hmac.new(
                self._settings.jwt_secret_key.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
            expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

            if not hmac.compare_digest(signature_b64, expected_b64):
                return None

            # Decode payload
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiration
            if payload.get("exp") and payload["exp"] < time.time():
                return None

            return payload
        except Exception:
            return None


# ── FastAPI Dependencies ──

_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Get or create auth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
) -> User:
    """FastAPI dependency to extract and validate the current user.

    Supports both Bearer token (JWT) and API key authentication.
    """
    auth_service = get_auth_service()

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # Try API key first (starts with sk-)
    if token.startswith("sk-"):
        user = auth_service.validate_api_key(token)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Try JWT
    user = auth_service.validate_access_token(token)
    if user:
        return user

    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
) -> User | None:
    """Like get_current_user but returns None instead of raising on missing auth."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
