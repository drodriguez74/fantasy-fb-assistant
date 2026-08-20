import httpx
from typing import Dict, List, Optional, Any
import asyncio
from datetime import datetime
import base64
import json
from app.core.config import settings


class YahooFantasyService:
    def __init__(self):
        self.client = httpx.AsyncClient()
        self.base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        self.oauth_url = "https://api.login.yahoo.com/oauth2"
        
        self.client_id = settings.YAHOO_CLIENT_ID
        self.client_secret = settings.YAHOO_CLIENT_SECRET
        self.access_token = None
        
        # Check if credentials are configured
        if not self.client_id or not self.client_secret:
            self.credentials_configured = False
        else:
            self.credentials_configured = True

    async def authenticate(self, authorization_code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        try:
            if not self.credentials_configured:
                return {"error": "Yahoo API credentials not configured"}
            
            # Prepare OAuth2 token exchange
            auth_header = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": redirect_uri
            }
            
            print(f"Yahoo OAuth: Requesting token with redirect_uri: {redirect_uri}")
            print(f"Yahoo OAuth: Authorization code length: {len(authorization_code)}")
            
            response = await self.client.post(
                f"{self.oauth_url}/get_token",
                headers=headers,
                data=data
            )
            
            print(f"Yahoo OAuth: Response status: {response.status_code}")
            
            if response.status_code != 200:
                error_text = response.text
                print(f"Yahoo OAuth Error: {error_text}")
                return {
                    "error": f"Yahoo OAuth failed with status {response.status_code}: {error_text}"
                }
            
            token_data = response.json()
            
            if "access_token" not in token_data:
                print(f"Yahoo OAuth: No access token in response: {token_data}")
                return {"error": f"No access token received from Yahoo: {token_data}"}
            
            self.access_token = token_data.get("access_token")
            print(f"Yahoo OAuth: Successfully obtained access token")
            
            return token_data
        except httpx.RequestError as e:
            print(f"Yahoo OAuth Request Error: {str(e)}")
            return {"error": f"Authentication request failed: {str(e)}"}
        except Exception as e:
            print(f"Yahoo OAuth Unexpected Error: {str(e)}")
            return {"error": f"Authentication failed: {str(e)}"}

    async def get_user_leagues(self, season: int = 2024) -> List[Dict[str, Any]]:
        """Get user's Yahoo Fantasy leagues"""
        if not self.access_token:
            return [{"error": "Not authenticated"}]
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/users;use_login=1/games;game_keys=nfl/leagues"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            # Yahoo returns XML by default, but we can request JSON
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            leagues = []
            fantasy_content = data.get("fantasy_content", {})
            users = fantasy_content.get("users", {}).get("0", {}).get("user", {})
            games = users.get("games", {})
            
            for game_key, game_data in games.items():
                if isinstance(game_data, dict) and "game" in game_data:
                    game = game_data["game"]
                    if game.get("code") == "nfl" and str(season) in game.get("season", ""):
                        game_leagues = game.get("leagues", {})
                        for league_key, league_data in game_leagues.items():
                            if isinstance(league_data, dict) and "league" in league_data:
                                league = league_data["league"]
                                leagues.append({
                                    "league_key": league.get("league_key"),
                                    "league_id": league.get("league_id"),
                                    "name": league.get("name"),
                                    "num_teams": league.get("num_teams"),
                                    "scoring_type": league.get("scoring_type"),
                                    "league_type": league.get("league_type")
                                })
            
            return leagues
        except httpx.RequestError as e:
            return [{"error": f"Failed to get leagues: {str(e)}"}]

    async def get_league_info(self, league_key: str) -> Dict[str, Any]:
        """Get Yahoo league information"""
        if not self.access_token:
            return {"error": "Not authenticated"}
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/league/{league_key}"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            league_data = data.get("fantasy_content", {}).get("league", {})
            
            return {
                "league_key": league_data.get("league_key"),
                "league_id": league_data.get("league_id"),
                "name": league_data.get("name"),
                "num_teams": league_data.get("num_teams"),
                "current_week": league_data.get("current_week"),
                "start_week": league_data.get("start_week"),
                "end_week": league_data.get("end_week"),
                "scoring_type": league_data.get("scoring_type"),
                "league_type": league_data.get("league_type"),
                "draft_status": league_data.get("draft_status")
            }
        except httpx.RequestError as e:
            return {"error": f"Failed to get league info: {str(e)}"}

    async def get_league_teams(self, league_key: str) -> List[Dict[str, Any]]:
        """Get all teams in Yahoo league"""
        if not self.access_token:
            return [{"error": "Not authenticated"}]
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/league/{league_key}/teams"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            teams = []
            teams_data = data.get("fantasy_content", {}).get("league", {}).get("teams", {})
            
            for team_key, team_data in teams_data.items():
                if isinstance(team_data, dict) and "team" in team_data:
                    team = team_data["team"]
                    teams.append({
                        "team_key": team.get("team_key"),
                        "team_id": team.get("team_id"),
                        "name": team.get("name"),
                        "manager": team.get("managers", {}).get("0", {}).get("manager", {}).get("nickname"),
                        "wins": team.get("team_standings", {}).get("outcome_totals", {}).get("wins"),
                        "losses": team.get("team_standings", {}).get("outcome_totals", {}).get("losses"),
                        "points_for": team.get("team_standings", {}).get("points_for"),
                        "points_against": team.get("team_standings", {}).get("points_against")
                    })
            
            return teams
        except httpx.RequestError as e:
            return [{"error": f"Failed to get teams: {str(e)}"}]

    async def get_team_roster(self, team_key: str, week: int = None) -> Dict[str, Any]:
        """Get roster for specific Yahoo team"""
        if not self.access_token:
            return {"error": "Not authenticated"}
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/team/{team_key}/roster"
            
            if week:
                url += f";week={week}"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            roster_data = data.get("fantasy_content", {}).get("team", {}).get("roster", {})
            
            players = []
            players_data = roster_data.get("players", {})
            
            for player_key, player_data in players_data.items():
                if isinstance(player_data, dict) and "player" in player_data:
                    player = player_data["player"]
                    players.append({
                        "player_key": player.get("player_key"),
                        "player_id": player.get("player_id"),
                        "name": player.get("name", {}).get("full"),
                        "position": player.get("eligible_positions", {}).get("position"),
                        "team": player.get("editorial_team_abbr"),
                        "selected_position": player.get("selected_position", {}).get("position"),
                        "status": player.get("status")
                    })
            
            return {
                "team_key": team_key,
                "week": week,
                "players": players
            }
        except httpx.RequestError as e:
            return {"error": f"Failed to get roster: {str(e)}"}

    async def get_available_players(self, league_key: str, position: str = None, count: int = 25) -> List[Dict[str, Any]]:
        """Get available players in Yahoo league"""
        if not self.access_token:
            return [{"error": "Not authenticated"}]
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/league/{league_key}/players"
            
            params = {
                "status": "A",  # Available players
                "count": count
            }
            
            if position:
                params["position"] = position
            
            response = await self.client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            available_players = []
            players_data = data.get("fantasy_content", {}).get("league", {}).get("players", {})
            
            for player_key, player_data in players_data.items():
                if isinstance(player_data, dict) and "player" in player_data:
                    player = player_data["player"]
                    available_players.append({
                        "player_key": player.get("player_key"),
                        "player_id": player.get("player_id"),
                        "name": player.get("name", {}).get("full"),
                        "position": player.get("eligible_positions", {}).get("position"),
                        "team": player.get("editorial_team_abbr"),
                        "ownership_percentage": player.get("percent_owned", {}).get("value"),
                        "status": player.get("status")
                    })
            
            return available_players
        except httpx.RequestError as e:
            return [{"error": f"Failed to get available players: {str(e)}"}]

    async def get_draft_results(self, league_key: str) -> List[Dict[str, Any]]:
        """Get draft results from Yahoo league"""
        if not self.access_token:
            return [{"error": "Not authenticated"}]
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/league/{league_key}/draftresults"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            draft_results = []
            results_data = data.get("fantasy_content", {}).get("league", {}).get("draft_results", {})
            
            for pick_key, pick_data in results_data.items():
                if isinstance(pick_data, dict) and "draft_result" in pick_data:
                    pick = pick_data["draft_result"]
                    draft_results.append({
                        "pick": pick.get("pick"),
                        "round": pick.get("round"),
                        "team_key": pick.get("team_key"),
                        "player_key": pick.get("player_key")
                    })
            
            return draft_results
        except httpx.RequestError as e:
            return [{"error": f"Failed to get draft results: {str(e)}"}]

    async def monitor_live_draft(self, league_key: str) -> Dict[str, Any]:
        """Monitor live draft progress"""
        if not self.access_token:
            return {"error": "Not authenticated"}
        
        try:
            # Get league info to check draft status
            league_info = await self.get_league_info(league_key)
            
            if "error" in league_info:
                return league_info
            
            draft_status = league_info.get("draft_status")
            
            if draft_status == "predraft":
                return {
                    "status": "predraft",
                    "message": "Draft has not started yet"
                }
            elif draft_status == "postdraft":
                # Get final draft results
                draft_results = await self.get_draft_results(league_key)
                return {
                    "status": "completed",
                    "draft_results": draft_results
                }
            else:
                # Draft in progress - get current available players
                available_players = await self.get_available_players(league_key, count=50)
                recent_picks = await self.get_draft_results(league_key)
                
                return {
                    "status": "in_progress",
                    "available_players": available_players[:20],
                    "recent_picks": recent_picks[-10:] if recent_picks else [],
                    "league_info": league_info
                }
        except Exception as e:
            return {"error": f"Failed to monitor draft: {str(e)}"}

    async def get_matchups(self, league_key: str, week: int) -> List[Dict[str, Any]]:
        """Get matchups for specific week"""
        if not self.access_token:
            return [{"error": "Not authenticated"}]
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self.base_url}/league/{league_key}/scoreboard;week={week}"
            
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            
            matchups = []
            scoreboard = data.get("fantasy_content", {}).get("league", {}).get("scoreboard", {})
            matchups_data = scoreboard.get("matchups", {})
            
            for matchup_key, matchup_data in matchups_data.items():
                if isinstance(matchup_data, dict) and "matchup" in matchup_data:
                    matchup = matchup_data["matchup"]
                    teams = matchup.get("teams", {})
                    
                    team1 = teams.get("0", {}).get("team", {})
                    team2 = teams.get("1", {}).get("team", {})
                    
                    matchups.append({
                        "week": week,
                        "team1": {
                            "team_key": team1.get("team_key"),
                            "name": team1.get("name"),
                            "points": team1.get("team_points", {}).get("total")
                        },
                        "team2": {
                            "team_key": team2.get("team_key"),
                            "name": team2.get("name"),
                            "points": team2.get("team_points", {}).get("total")
                        }
                    })
            
            return matchups
        except httpx.RequestError as e:
            return [{"error": f"Failed to get matchups: {str(e)}"}]

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


yahoo_service = YahooFantasyService()