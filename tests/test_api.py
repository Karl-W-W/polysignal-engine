"""
Tests for core/api.py — Flask REST API endpoints.

Note: core.api imports from workflows.masterloop at load time,
so we must mock that module before importing core.api.
"""

import sys
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def client():
    """Create a Flask test client with mocked dependencies."""
    # Mock the heavy workflows module before core.api tries to import it
    mock_masterloop = MagicMock()
    mock_masterloop.run_cycle = MagicMock(return_value={})
    sys.modules.setdefault("workflows", MagicMock())
    sys.modules["workflows.masterloop"] = mock_masterloop

    # Now safe to import core.api
    import importlib
    if "core.api" in sys.modules:
        importlib.reload(sys.modules["core.api"])
    from core.api import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "operational"
        assert "brain" in data


class TestStatusEndpoint:
    def test_status_returns_state(self, client):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "cycle_number" in data
        assert "execution_status" in data


class TestSystemStats:
    def test_stats_returns_gracefully_without_db(self, client):
        """Stats should not crash even if DB is missing."""
        response = client.get("/api/system/stats")
        assert response.status_code == 200
        data = response.get_json()
        assert "status" in data
        assert "cards_processed" in data


class TestNarrativeEndpoint:
    def test_narrative_returns_list(self, client):
        """Narrative should return an empty list if DB has no data."""
        response = client.get("/api/narrative/latest")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
