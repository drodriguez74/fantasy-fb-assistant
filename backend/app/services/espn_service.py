import httpx
from typing import Dict, List, Optional, Any
import asyncio
from datetime import datetime
from app.core.config import settings


class ESPNFantasyService:
    def __init__(self):
        self.client = httpx.AsyncClient()
        self.base_url = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
        
        # ESPN Fantasy requires these headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json'
        }

    async def get_league_info(self, league_id: str, season: int = 2024) -> Dict[str, Any]:
        """Get ESPN league information"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            response = await self.client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            return {"error": f"Failed to get league info: {str(e)}"}

    async def get_league_teams(self, league_id: str, season: int = 2024) -> List[Dict[str, Any]]:
        """Get all teams in an ESPN league"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {"view": "mTeam"}
            
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            return data.get("teams", [])
        except httpx.RequestError as e:
            return [{"error": f"Failed to get teams: {str(e)}"}]

    async def get_league_rosters(self, league_id: str, season: int = 2024, week: int = None) -> List[Dict[str, Any]]:
        """Get rosters for all teams in ESPN league"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {"view": "mRoster"}
            
            if week:
                params["scoringPeriodId"] = week
            
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            rosters = []
            for team in data.get("teams", []):
                roster = {
                    "team_id": team.get("id"),
                    "team_name": team.get("location", "") + " " + team.get("nickname", ""),
                    "players": []
                }
                
                for entry in team.get("roster", {}).get("entries", []):
                    player = entry.get("playerPoolEntry", {}).get("player", {})
                    roster["players"].append({
                        "id": player.get("id"),
                        "name": player.get("fullName"),
                        "position": self._convert_position(player.get("defaultPositionId")),
                        "team": self._get_team_name(player.get("proTeamId")),
                        "injury_status": player.get("injuryStatus"),
                        "lineup_slot": entry.get("lineupSlotId")
                    })
                
                rosters.append(roster)
            
            return rosters
        except httpx.RequestError as e:
            return [{"error": f"Failed to get rosters: {str(e)}"}]

    async def get_available_players(self, league_id: str, season: int = 2024, size: int = 50) -> List[Dict[str, Any]]:
        """Get available players on waivers/free agency"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {
                "view": "kona_player_info",
                "scoringPeriodId": 0,
                "size": size
            }
            
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            available_players = []
            for player_data in data.get("players", []):
                player = player_data.get("player", {})
                
                # Only include available players (not on any roster)
                if player_data.get("onTeamId") == 0:
                    available_players.append({
                        "id": player.get("id"),
                        "name": player.get("fullName"),
                        "position": self._convert_position(player.get("defaultPositionId")),
                        "team": self._get_team_name(player.get("proTeamId")),
                        "ownership": player_data.get("ownership", {}).get("percentOwned", 0),
                        "projected_points": self._get_projected_points(player),
                        "injury_status": player.get("injuryStatus"),
                        "stats": self._get_player_stats(player)
                    })
            
            return available_players
        except httpx.RequestError as e:
            return [{"error": f"Failed to get available players: {str(e)}"}]

    async def get_draft_info(self, league_id: str, season: int = 2024) -> Dict[str, Any]:
        """Get draft information for ESPN league"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {"view": "mDraftDetail"}
            
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            draft_detail = data.get("draftDetail", {})
            
            return {
                "draft_id": draft_detail.get("id"),
                "draft_type": draft_detail.get("type"),
                "is_complete": draft_detail.get("completed", False),
                "current_pick": draft_detail.get("picks", {}).get("currentPick", 0),
                "total_picks": len(draft_detail.get("picks", [])),
                "draft_order": self._get_draft_order(draft_detail),
                "picks": self._format_draft_picks(draft_detail.get("picks", []))
            }
        except httpx.RequestError as e:
            return {"error": f"Failed to get draft info: {str(e)}"}

    async def get_matchup_info(self, league_id: str, season: int = 2024, week: int = None) -> List[Dict[str, Any]]:
        """Get matchup information for specific week"""
        try:
            url = f"{self.base_url}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {"view": "mMatchup"}
            
            if week:
                params["scoringPeriodId"] = week
            
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            matchups = []
            for matchup in data.get("schedule", []):
                matchups.append({
                    "matchup_id": matchup.get("id"),
                    "week": matchup.get("matchupPeriodId"),
                    "home_team": {
                        "id": matchup.get("home", {}).get("teamId"),
                        "score": matchup.get("home", {}).get("totalPoints", 0)
                    },
                    "away_team": {
                        "id": matchup.get("away", {}).get("teamId"),
                        "score": matchup.get("away", {}).get("totalPoints", 0)
                    }
                })
            
            return matchups
        except httpx.RequestError as e:
            return [{"error": f"Failed to get matchups: {str(e)}"}]

    async def monitor_draft_progress(self, league_id: str, season: int = 2024) -> Dict[str, Any]:
        """Monitor live draft progress"""
        try:
            draft_info = await self.get_draft_info(league_id, season)
            
            if "error" in draft_info:
                return draft_info
            
            if not draft_info.get("is_complete", True):
                # Draft is in progress
                available_players = await self.get_available_players(league_id, season, 100)
                
                return {
                    "draft_status": "in_progress",
                    "current_pick": draft_info.get("current_pick", 0),
                    "total_picks": draft_info.get("total_picks", 0),
                    "available_players": available_players[:20],  # Top 20 available
                    "recent_picks": draft_info.get("picks", [])[-5:],  # Last 5 picks
                    "draft_order": draft_info.get("draft_order", [])
                }
            else:
                return {
                    "draft_status": "completed",
                    "final_picks": draft_info.get("picks", [])
                }
        except Exception as e:
            return {"error": f"Failed to monitor draft: {str(e)}"}

    def _convert_position(self, position_id: int) -> str:
        """Convert ESPN position ID to standard position"""
        position_map = {
            1: "QB", 2: "RB", 3: "WR", 4: "TE", 
            5: "K", 16: "DEF", 17: "DEF"
        }
        return position_map.get(position_id, "UNKNOWN")

    def _get_team_name(self, team_id: int) -> str:
        """Convert ESPN team ID to team abbreviation"""
        # This is a simplified mapping - ESPN uses numeric team IDs
        team_map = {
            1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 
            7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 
            13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 
            19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 
            25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 
            33: "BAL", 34: "HOU"
        }
        return team_map.get(team_id, "FA")

    def _get_projected_points(self, player: Dict[str, Any]) -> float:
        """Extract projected points from player data"""
        try:
            stats = player.get("stats", [])
            for stat in stats:
                if stat.get("statSourceId") == 1:  # Projected stats
                    return stat.get("appliedTotal", 0.0)
            return 0.0
        except:
            return 0.0

    def _get_player_stats(self, player: Dict[str, Any]) -> Dict[str, Any]:
        """Extract player statistics"""
        try:
            stats = player.get("stats", [])
            player_stats = {}
            
            for stat in stats:
                if stat.get("statSourceId") == 0:  # Actual stats
                    player_stats["actual"] = stat.get("appliedTotal", 0.0)
                elif stat.get("statSourceId") == 1:  # Projected stats
                    player_stats["projected"] = stat.get("appliedTotal", 0.0)
            
            return player_stats
        except:
            return {}

    def _get_draft_order(self, draft_detail: Dict[str, Any]) -> List[int]:
        """Extract draft order from draft detail"""
        try:
            return draft_detail.get("draftOrder", [])
        except:
            return []

    def _format_draft_picks(self, picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format draft picks for easier consumption"""
        formatted_picks = []
        
        for pick in picks:
            formatted_picks.append({
                "pick_number": pick.get("id"),
                "round": pick.get("roundId"),
                "team_id": pick.get("teamId"),
                "player_id": pick.get("playerId"),
                "keeper": pick.get("keeper", False)
            })
        
        return formatted_picks

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


espn_service = ESPNFantasyService()