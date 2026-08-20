"""
Utility for loading real connected league data consistently across all endpoints
"""
import json
from typing import Dict, Optional, Any
from pathlib import Path

CONNECTED_LEAGUE_FILE = "/Users/darwinrodriguez/projects/fantasy-football-assistant/backend/connected_league.json"

def load_connected_league_data() -> Optional[Dict[str, Any]]:
    """Load connected league data from file"""
    try:
        with open(CONNECTED_LEAGUE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None

def get_league_info(league_id: int = 1) -> Dict[str, Any]:
    """Get league info for a given league ID, using real data if available"""
    connection_data = load_connected_league_data()
    
    if connection_data and connection_data.get("espn_league_id") and league_id == 1:
        return {
            "id": league_id,
            "name": f"ESPN League {connection_data['espn_league_id']}",
            "league_key": connection_data["espn_league_id"],
            "platform": "ESPN",
            "scoring_format": connection_data.get("scoring_format", "PPR"),
            "league_size": connection_data.get("league_size", 10),
            "season": connection_data.get("season", 2025),
            "is_active": True,
            "espn_league_id": connection_data["espn_league_id"],
            "espn_swid": connection_data.get("espn_swid"),
            "espn_s2": connection_data.get("espn_s2"),
            "connected_at": connection_data.get("connected_at")
        }
    else:
        # Fallback demo data with 2025 season
        return {
            "id": league_id,
            "name": "Demo ESPN League",
            "league_key": "12345",
            "platform": "ESPN",
            "scoring_format": "PPR",
            "league_size": 10,
            "season": 2025,
            "is_active": True
        }

def get_all_user_leagues() -> list[Dict[str, Any]]:
    """Get all user leagues, using real data if available"""
    connection_data = load_connected_league_data()
    
    leagues = []
    
    if connection_data and connection_data.get("espn_league_id"):
        # Add real ESPN league
        leagues.append({
            "id": 1,
            "name": f"ESPN League {connection_data['espn_league_id']}",
            "league_key": connection_data["espn_league_id"],
            "platform": "ESPN",
            "scoring_format": connection_data.get("scoring_format", "PPR"),
            "league_size": connection_data.get("league_size", 10),
            "season": connection_data.get("season", 2025),
            "is_active": True,
            "team_id": "1",
            "user_id": 1,
            "is_commissioner": False,
            "added_at": connection_data.get("connected_at", "2025-09-01T20:35:00.000Z")
        })
    else:
        # Fallback demo data
        leagues.append({
            "id": 1,
            "name": "Demo ESPN League",
            "league_key": "12345",
            "platform": "ESPN",
            "scoring_format": "PPR",
            "league_size": 10,
            "season": 2025,
            "is_active": True,
            "team_id": "1",
            "user_id": 1,
            "is_commissioner": False,
            "added_at": "2025-09-01T20:35:00.000Z"
        })
    
    return leagues

def is_real_league_connected() -> bool:
    """Check if a real league is connected"""
    connection_data = load_connected_league_data()
    return connection_data is not None and connection_data.get("espn_league_id") is not None