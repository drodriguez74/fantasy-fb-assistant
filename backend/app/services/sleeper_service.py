import httpx
from typing import Dict, List, Optional, Any
from app.core.config import settings
import asyncio
from datetime import datetime


class SleeperService:
    def __init__(self):
        self.base_url = settings.SLEEPER_API_URL
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def client(self) -> httpx.AsyncClient:
        # A single AsyncClient created eagerly (e.g. at module import time) binds
        # its connection pool to whichever event loop is running when it's first
        # used. Reusing it from a *different* loop later (e.g. successive
        # TestClient requests, each running their own loop) raises
        # "Event loop is closed". Recreate the client whenever the running loop
        # changes so it always matches the loop making the request.
        loop = asyncio.get_event_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = httpx.AsyncClient()
            self._client_loop = loop
        return self._client

    async def get_nfl_state(self) -> Dict[str, Any]:
        """Get current NFL season state"""
        try:
            response = await self.client.get(f"{self.base_url}/state/nfl")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_all_players(self) -> Dict[str, Any]:
        """Get all NFL players"""
        try:
            response = await self.client.get(f"{self.base_url}/players/nfl")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_player_stats(self, player_id: str, season: str = "2024") -> Dict[str, Any]:
        """Get player stats for a specific season including weekly data"""
        try:
            # Get season totals
            season_response = await self.client.get(f"{self.base_url}/stats/nfl/regular/{season}")
            season_response.raise_for_status()
            season_stats = season_response.json()
            player_season_stats = season_stats.get(player_id, {})
            
            # Get weekly stats for each week
            weekly_stats = {}
            for week in range(1, 19):  # NFL regular season weeks 1-18
                try:
                    week_response = await self.client.get(f"{self.base_url}/stats/nfl/regular/{season}/{week}")
                    week_response.raise_for_status()
                    week_data = week_response.json()
                    
                    if player_id in week_data:
                        weekly_stats[str(week)] = week_data[player_id]
                        
                except (httpx.RequestError, httpx.HTTPStatusError):
                    # Week might not exist yet or player didn't play
                    continue
                    
            # Combine season and weekly stats
            return {
                "season_totals": player_season_stats,
                "weekly": weekly_stats
            }
            
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_trending_players(self, 
                                   trend_type: str = "add", 
                                   lookback_hours: int = 24,
                                   limit: int = 25) -> List[Dict[str, Any]]:
        """Get trending players (adds/drops)"""
        try:
            response = await self.client.get(
                f"{self.base_url}/players/nfl/trending/{trend_type}",
                params={
                    "lookback_hours": lookback_hours,
                    "limit": limit
                }
            )
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_player_projections(self, week: int, season: str = "2024") -> Dict[str, Any]:
        """Get player projections for a specific week"""
        try:
            response = await self.client.get(f"{self.base_url}/projections/nfl/{season}/{week}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_user_leagues(self, user_id: str, season: str = "2024") -> List[Dict[str, Any]]:
        """Get leagues for a specific user"""
        try:
            response = await self.client.get(f"{self.base_url}/user/{user_id}/leagues/nfl/{season}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_league_info(self, league_id: str) -> Dict[str, Any]:
        """Get league information"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_league_rosters(self, league_id: str) -> List[Dict[str, Any]]:
        """Get all rosters in a league"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}/rosters")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_league_users(self, league_id: str) -> List[Dict[str, Any]]:
        """Get all users in a league"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}/users")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_matchups(self, league_id: str, week: int) -> List[Dict[str, Any]]:
        """Get matchups for a specific week"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}/matchups/{week}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_transactions(self, league_id: str, week: int) -> List[Dict[str, Any]]:
        """Get transactions for a specific week"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}/transactions/{week}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_waiver_candidates(self, league_id: str) -> List[Dict[str, Any]]:
        """Get potential waiver wire candidates based on ownership and trends"""
        try:
            # Get trending adds
            trending = await self.get_trending_players("add", 24, 50)
            
            # Get league rosters to determine available players
            rosters = await self.get_league_rosters(league_id)
            
            # Extract rostered player IDs
            rostered_players = set()
            for roster in rosters:
                if "players" in roster and roster["players"]:
                    rostered_players.update(roster["players"])
            
            # Filter trending players that aren't rostered
            available_trending = []
            for player in trending:
                if isinstance(player, dict) and "player_id" in player:
                    if player["player_id"] not in rostered_players:
                        available_trending.append(player)
            
            return available_trending[:25]  # Return top 25
            
        except Exception as e:
            return [{"error": f"Failed to get waiver candidates: {str(e)}"}]

    async def get_league_drafts(self, league_id: str) -> List[Dict[str, Any]]:
        """Get all drafts for a league"""
        try:
            response = await self.client.get(f"{self.base_url}/league/{league_id}/drafts")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_draft_info(self, draft_id: str) -> Dict[str, Any]:
        """Get draft information"""
        try:
            response = await self.client.get(f"{self.base_url}/draft/{draft_id}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_draft_picks(self, draft_id: str) -> List[Dict[str, Any]]:
        """Get all picks in a draft"""
        try:
            response = await self.client.get(f"{self.base_url}/draft/{draft_id}/picks")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_user_drafts(self, user_id: str, sport: str = "nfl", season: str = "2024") -> List[Dict[str, Any]]:
        """Get all drafts by a user"""
        try:
            response = await self.client.get(f"{self.base_url}/user/{user_id}/drafts/{sport}/{season}")
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Request failed: {str(e)}"}]

    async def get_draft_state(self, league_id: str) -> Dict[str, Any]:
        """Get live draft state for a league"""
        try:
            # Get all drafts for the league
            drafts = await self.get_league_drafts(league_id)
            
            if not drafts or (isinstance(drafts, list) and len(drafts) > 0 and "error" in drafts[0]):
                return {"error": "No drafts found for league"}
            
            if not isinstance(drafts, list) or len(drafts) == 0:
                return {"error": "No drafts found for league"}
            
            # Find the most recent draft
            current_draft = None
            for draft in drafts:
                if draft.get("status") in ["drafting", "complete"]:
                    current_draft = draft
                    break
            
            if not current_draft:
                return {"error": "No active or completed draft found"}
            
            draft_id = current_draft["draft_id"]
            
            # Get draft details
            draft_info = await self.get_draft_info(draft_id)
            if "error" in draft_info:
                return draft_info
            
            # Get draft picks
            picks = await self.get_draft_picks(draft_id)
            if not isinstance(picks, list) or (len(picks) > 0 and "error" in picks[0]):
                picks = []
            
            # Get league info for context
            league_info = await self.get_league_info(league_id)
            
            # Calculate available players by getting all players and filtering out drafted ones
            all_players = await self.get_all_players()
            drafted_player_ids = {pick["player_id"] for pick in picks if pick.get("player_id")}
            
            # Filter available players (simplified - could be enhanced with position filtering)
            available_players = []
            if not isinstance(all_players, dict) or "error" not in all_players:
                for player_id, player_data in list(all_players.items())[:100]:  # Limit to first 100
                    if player_id not in drafted_player_ids and isinstance(player_data, dict):
                        player_data["player_id"] = player_id
                        available_players.append(player_data)
            
            # Get trending players
            trending = await self.get_trending_players("add", 24, 25)
            
            # Calculate current pick number
            total_picks_made = len([p for p in picks if p.get("player_id")])
            total_teams = draft_info.get("settings", {}).get("teams", 12)
            total_rounds = draft_info.get("settings", {}).get("rounds", 16)
            
            return {
                "status": draft_info.get("status", "unknown"),
                "draft_id": draft_id,
                "current_pick": total_picks_made + 1,
                "total_picks": total_teams * total_rounds,
                "available_players": available_players[:50],  # Limit response size
                "trending_players": trending,
                "draft_info": draft_info,
                "picks": picks,
                "league_info": league_info
            }
            
        except Exception as e:
            return {"error": f"Failed to get draft state: {str(e)}"}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


sleeper_service = SleeperService()