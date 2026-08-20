"""
Tests for player endpoints
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_get_players(client):
    """Test getting list of players"""
    response = client.get("/api/v1/players/")
    assert response.status_code == 200
    data = response.json()
    assert "players" in data
    assert isinstance(data["players"], list)

def test_search_players(client):
    """Test player search functionality"""
    # Test with a common name
    response = client.get("/api/v1/players/search/allen")
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)

def test_get_player_by_id(client):
    """Test getting specific player by ID"""
    # First get a list of players
    players_response = client.get("/api/v1/players/?limit=1")
    players_data = players_response.json()
    
    if players_data.get("players"):
        player_id = players_data["players"][0]["id"]
        response = client.get(f"/api/v1/players/{player_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == player_id

def test_player_filters(client):
    """Test player filtering by position"""
    response = client.get("/api/v1/players/?position=QB")
    assert response.status_code == 200
    data = response.json()
    
    # Check that all returned players are QBs
    if data.get("players"):
        for player in data["players"]:
            assert player["position"] == "QB"