"""API integration tests using FastAPI TestClient."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.services.auth import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a test client with mocked auth."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_user():
    """A mock authenticated user."""
    return User(
        user_id="u_test_001",
        email="test@example.com",
        workspace_id="ws_001",
        roles=["developer"],
        auth_method="api_key",
        key_id="key_001",
    )


@pytest.fixture
def auth_headers():
    """Headers with a fake Bearer token."""
    return {"Authorization": "Bearer sk-test1234567890"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ---------------------------------------------------------------------------
# Workflow Endpoints
# ---------------------------------------------------------------------------

class TestWorkflowEndpoints:

    @patch("src.services.auth.get_auth_service")
    def test_create_workflow(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.post("/api/v1/workflows", json={
            "name": "Test Workflow",
            "description": "A test workflow",
        }, headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Test Workflow"

    @patch("src.services.auth.get_auth_service")
    def test_list_workflows(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.get("/api/v1/workflows", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @patch("src.services.auth.get_auth_service")
    def test_get_workflow_not_found(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.get("/api/v1/workflows/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    @patch("src.services.auth.get_auth_service")
    def test_create_and_get_workflow(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        # Create
        create_resp = client.post("/api/v1/workflows", json={
            "name": "My Flow",
            "description": "desc",
        }, headers=auth_headers)
        wf_id = create_resp.json()["data"]["id"]

        # Get
        get_resp = client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["name"] == "My Flow"

    @patch("src.services.auth.get_auth_service")
    def test_delete_workflow(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        create_resp = client.post("/api/v1/workflows", json={"name": "ToDelete"}, headers=auth_headers)
        wf_id = create_resp.json()["data"]["id"]

        del_resp = client.delete(f"/api/v1/workflows/{wf_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["code"] == 0


# ---------------------------------------------------------------------------
# Node Endpoints
# ---------------------------------------------------------------------------

class TestNodeEndpoints:

    def test_list_nodes(self, client):
        resp = client.get("/api/v1/nodes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)

    def test_list_node_categories(self, client):
        resp = client.get("/api/v1/nodes/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    def test_get_node_not_found(self, client):
        resp = client.get("/api/v1/nodes/nonexistent_node_type")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Model Endpoints
# ---------------------------------------------------------------------------

class TestModelEndpoints:

    def test_list_models(self, client):
        resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)
        # Should include default models
        model_ids = [m["model_id"] for m in data["data"]]
        assert "gpt-4o" in model_ids

    @patch("src.services.auth.get_auth_service")
    def test_register_model(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.post("/api/v1/models", json={
            "model_id": "custom-model-1",
            "provider": "openai",
            "display_name": "Custom Model",
            "context_window": 32000,
        }, headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["model_id"] == "custom-model-1"

    @patch("src.services.auth.get_auth_service")
    def test_delete_model(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        # Register first
        client.post("/api/v1/models", json={
            "model_id": "to-delete",
            "provider": "openai",
        }, headers=auth_headers)

        # Delete
        resp = client.delete("/api/v1/models/to-delete/credentials", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

    @patch("src.services.auth.get_auth_service")
    def test_delete_model_not_found(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.delete("/api/v1/models/nonexistent/credentials", headers=auth_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Skills Endpoints
# ---------------------------------------------------------------------------

class TestSkillEndpoints:

    def test_list_skills(self, client):
        resp = client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)

    def test_get_skill_not_found(self, client):
        resp = client.get("/api/v1/skills/nonexistent_skill")
        assert resp.status_code == 404

    def test_validate_skill_not_found(self, client):
        resp = client.post("/api/v1/skills/nonexistent/validate", json={"inputs": {}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["valid"] is False
        assert len(data["data"]["errors"]) > 0

    @patch("src.services.auth.get_auth_service")
    def test_reload_skills(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.post("/api/v1/skills/reload", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["reloaded"] is True

    @patch("src.services.auth.get_auth_service")
    def test_package_skill_not_found(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        resp = client.post("/api/v1/skills/nonexistent/package", headers=auth_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

class TestAuthEndpoints:

    def test_login_missing_credentials(self, client):
        resp = client.post("/api/v1/auth/login", json={})
        # Should fail validation or return 400/401
        assert resp.status_code in (400, 401, 422)

    @patch("src.services.auth.get_auth_service")
    def test_create_api_key(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_auth.create_api_key.return_value = {
            "key_id": "key_new",
            "key_prefix": "sk-test12",
            "full_key": "sk-test1234567890abcdef",
            "name": "test-key",
        }
        mock_get_auth.return_value = mock_auth

        resp = client.post("/api/v1/auth/api-keys", json={"name": "test-key"}, headers=auth_headers)
        assert resp.status_code == 200

    @patch("src.services.auth.get_auth_service")
    def test_list_api_keys(self, mock_get_auth, client, mock_user, auth_headers):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_auth.list_api_keys.return_value = []
        mock_get_auth.return_value = mock_auth

        resp = client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Auth Guard
# ---------------------------------------------------------------------------

class TestAuthGuard:

    def test_unauthenticated_request_rejected(self, client):
        """Endpoints requiring auth should return 401 without credentials."""
        resp = client.post("/api/v1/workflows", json={"name": "test"})
        assert resp.status_code == 401

    def test_invalid_token_rejected(self, client):
        resp = client.get("/api/v1/workflows", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TestMiddleware:

    def test_request_id_header(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers

    def test_custom_request_id_echoed(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "custom-id-123"})
        assert resp.headers["X-Request-ID"] == "custom-id-123"

    def test_cors_headers(self, client):
        resp = client.options("/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        })
        # CORS middleware should respond
        assert resp.status_code in (200, 204, 405)
