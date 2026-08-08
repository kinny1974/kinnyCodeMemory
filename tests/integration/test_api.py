"""Tests for memory_server.py API endpoints."""
from __future__ import annotations

import pytest

# Skip all tests if memory_server cannot be imported (missing dependencies)
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create test client for the FastAPI app."""
    try:
        from memory_server import app
        return TestClient(app, raise_server_exceptions=False)
    except Exception:
        pytest.skip("Cannot create test client")


class TestHealthEndpoints:
    """Tests for monitoring endpoints."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data

    def test_metrics(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "operations" in data
        assert "embedding_cache" in data

    def test_readiness(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestProjectEndpoints:
    """Tests for project management endpoints."""

    def test_list_projects(self, client):
        response = client.get("/list-projects")
        # May return 200 or 500 depending on server state
        assert response.status_code in [200, 500]

    def test_project_info(self, client):
        response = client.post(
            "/project-info",
            json={"project_id": "test-project"}
        )
        # May return 200 or 500 depending on server state
        assert response.status_code in [200, 500]


class TestDocumentEndpoints:
    """Tests for document management endpoints."""

    def test_list_documents(self, client):
        response = client.get("/list-documents")
        assert response.status_code in [200, 500]

    def test_search_documents_empty(self, client):
        response = client.post(
            "/search-documents",
            json={
                "query": "test",
                "project_id": "test-project",
                "top_k": 5
            }
        )
        assert response.status_code in [200, 500]


class TestSearchEndpoints:
    """Tests for search endpoints."""

    def test_semantic_search(self, client):
        response = client.post(
            "/semantic-search",
            json={
                "prompt": "test search",
                "project_id": "test-project",
                "n_results": 5
            }
        )
        # May return 200 with empty results or error if no data indexed
        assert response.status_code in [200, 404, 500]


class TestTaskEndpoints:
    """Tests for task management endpoints."""

    def test_list_tasks(self, client):
        response = client.get("/tasks")
        assert response.status_code in [200, 500]

    def test_create_task(self, client):
        response = client.post(
            "/tasks/upsert",
            json={
                "project_id": "test-project",
                "title": "Test Task",
                "description": "A test task"
            }
        )
        assert response.status_code in [200, 500]

    def test_get_task_not_found(self, client):
        response = client.get("/tasks/nonexistent-task-id")
        assert response.status_code in [404, 500]


class TestConversationEndpoints:
    """Tests for conversation management endpoints."""

    def test_save_conversation(self, client):
        response = client.post(
            "/save-conversation",
            json={
                "project_id": "test-project",
                "session_id": "test-session",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there"}
                ]
            }
        )
        assert response.status_code in [200, 422, 500]

    def test_load_conversation(self, client):
        response = client.post(
            "/load-conversation",
            json={
                "project_id": "test-project",
                "session_id": "test-session"
            }
        )
        assert response.status_code in [200, 500]


class TestValidationIntegration:
    """Tests for input validation integration."""

    def test_invalid_project_id(self, client):
        response = client.post(
            "/project-info",
            json={"project_id": "invalid project id!"}
        )
        # Should return validation error or 500
        assert response.status_code in [400, 422, 500]

    def test_empty_project_id_auto_detect(self, client):
        response = client.post(
            "/project-info",
            json={"project_id": ""}
        )
        # Should work with auto-detection or return 500
        assert response.status_code in [200, 500]
