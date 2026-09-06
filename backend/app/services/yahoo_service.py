import httpx
from typing import Dict, List, Optional, Any
import asyncio
import logging
from datetime import datetime
import base64
import json
from app.core.config import settings

logger = logging.getLogger(__name__)


class YahooFantasyService:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None
        self.base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        self.oauth_url = "https://api.login.yahoo.com/oauth2"

        self.client_id = settings.YAHOO_CLIENT_ID
        self.client_secret = settings.YAHOO_CLIENT_SECRET

        # NOTE: no self.access_token here. This service is a single
        # module-level singleton (see the bottom of this file) shared by
        # every request in the process, so per-user OAuth tokens must never
        # be stored as instance state -- that would silently leak one
        # user's Yahoo session into another user's requests. Every method
        # below that talks to Yahoo's API takes the caller's access_token
        # as an explicit parameter instead, mirroring how
        # espn_service_enhanced.py takes swid/espn_s2 as explicit params
        # rather than storing them on self. Callers are expected to load
        # the token from the caller's own UserLeague row (or wherever it
        # is scoped) and pass it in.

        # Check if credentials are configured
        if not self.client_id or not self.client_secret:
            self.credentials_configured = False
        else:
            self.credentials_configured = True

    @staticmethod
    def _error_detail(e: Exception) -> str:
        """httpx.HTTPStatusError's default str() is just the status code and
        URL -- it discards the response body, which for Yahoo's API usually
        names the actual reason (bad scope, revoked token, etc).

        Always logs the FULL untruncated detail server-side (this file had
        zero logging on this path before -- a live 403 here produced no
        terminal output at all, nothing to diagnose from). The returned
        string is deliberately short: frontend/src/services/api.ts treats
        any error message over 300 chars as "looks like a raw server
        error" and silently replaces it with a generic fallback, so a long
        "helpful" detail here was actually making the UI show *less*
        information than before this method existed.
        """
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            body = e.response.text.strip()
            if status == 403 and "not authorized to perform this action" in body:
                logger.error(f"Yahoo API 403 for {e.request.url}: {body}")
                return (
                    "Yahoo returned 403: this app's App ID is not yet whitelisted "
                    "for the Fantasy Sports API. OAuth works but fantasy data is "
                    "locked server-side until Yahoo support activates it."
                )
            if body:
                logger.error(f"Yahoo API {status} for {e.request.url}: {body}")
                # Response bodies are commonly XML/JSON with real structure;
                # a short prefix is usually enough to identify the reason
                # (e.g. an error code/message) without re-triggering the
                # frontend's raw-error-length filter.
                return f"Yahoo API returned {status}: {body[:150]}"
            logger.error(f"Yahoo API {status} for {e.request.url}: <empty response body>")
        else:
            logger.error(f"Yahoo API request failed: {e}")
        return str(e)

    @property
    def client(self) -> httpx.AsyncClient:
        # See SleeperService.client for why this is lazy/loop-aware rather than
        # a single client created once in __init__.
        loop = asyncio.get_event_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = httpx.AsyncClient()
            self._client_loop = loop
        return self._client

    async def authenticate(self, authorization_code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange an OAuth2 authorization code for a token pair.

        Returns Yahoo's raw token response on success, e.g.
        {"access_token": ..., "refresh_token": ..., "expires_in": ..., "token_type": "bearer", ...}
        Does NOT store the token anywhere -- the caller is responsible for
        persisting it (scoped to the right user) and passing it into the
        other methods on this service.
        """
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
                print(f"Yahoo OAuth: No access token in response")
                return {"error": "No access token received from Yahoo"}

            # Log the scope Yahoo *actually* granted (not what we requested).
            # A newly-created Fantasy Sports app stays locked server-side until
            # Yahoo support manually whitelists the App ID: the consent screen
            # accepts scope=fspt-w and a token is issued, but the granted scope
            # comes back WITHOUT fspt-w and every fantasysports.yahooapis.com
            # call 403s "This application is not authorized to perform this
            # action". If the line below shows no "fspt" scope, that's the
            # cause -- it is not a bug in this code.
            granted_scope = token_data.get("scope") or token_data.get("xoauth_yahoo_scope") or "<none returned>"
            print(f"Yahoo OAuth: Successfully obtained access token")
            print(f"Yahoo OAuth: granted scope: {granted_scope} (requested fspt-w)")
            if "fspt" not in str(granted_scope):
                print(
                    "Yahoo OAuth: WARNING -- no fantasy (fspt) scope granted. "
                    "Fantasy API calls will 403 until Yahoo support whitelists "
                    "this App ID for Fantasy Sports API access."
                )

            return token_data
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"Yahoo OAuth Request Error: {str(e)}")
            return {"error": f"Authentication request failed: {str(e)}"}
        except Exception as e:
            print(f"Yahoo OAuth Unexpected Error: {str(e)}")
            return {"error": f"Authentication failed: {str(e)}"}

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Exchange a refresh token for a new access token, per Yahoo's
        OAuth2 refresh flow (grant_type=refresh_token on the same token
        endpoint used by authenticate()). Returns the same shape as
        authenticate() on success: {"access_token": ..., "refresh_token": ...,
        "expires_in": ..., ...}. Does not persist anything -- the caller is
        responsible for storing the refreshed credentials.
        """
        try:
            if not self.credentials_configured:
                return {"error": "Yahoo API credentials not configured"}

            if not refresh_token:
                return {"error": "No refresh token provided"}

            auth_header = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()

            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }

            response = await self.client.post(
                f"{self.oauth_url}/get_token",
                headers=headers,
                data=data
            )

            if response.status_code != 200:
                error_text = response.text
                print(f"Yahoo OAuth Refresh Error: {error_text}")
                return {
                    "error": f"Yahoo token refresh failed with status {response.status_code}: {error_text}"
                }

            token_data = response.json()

            if "access_token" not in token_data:
                return {"error": "No access token received from Yahoo refresh"}

            return token_data
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Token refresh request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Token refresh failed: {str(e)}"}

    async def get_user_leagues(self, access_token: str, season: int = 2024) -> List[Dict[str, Any]]:
        """Get user's Yahoo Fantasy leagues"""
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/users;use_login=1/games;game_keys=nfl/leagues"

            # Yahoo returns XML by default; every parser below expects JSON.
            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get leagues: {self._error_detail(e)}"}]

    async def get_league_info(self, access_token: str, league_key: str) -> Dict[str, Any]:
        """Get Yahoo league information"""
        if not access_token:
            return {"error": "Not authenticated"}

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Failed to get league info: {self._error_detail(e)}"}

    async def get_league_settings(self, access_token: str, league_key: str) -> Dict[str, Any]:
        """Real, granular roster-slot counts and points-per-reception for a
        Yahoo league, read from the league's `settings` sub-resource
        (`/league/{league_key}/settings`) -- a separate real Yahoo Fantasy
        API resource from the base league info `get_league_info` above
        fetches, which doesn't carry any of this.

        Per Yahoo's Fantasy Sports API (confirmed via the settings resource
        field set several third-party API wrappers -- e.g. yfpy's Settings/
        RosterPosition/StatModifiers/Stat model classes -- expose from real
        Yahoo responses, since Yahoo's own developer docs are no longer
        reachable): `settings.roster_positions` is a list of real slots,
        each with a `position` label (e.g. "QB", "WR", "BN", "IR", or a
        multi-eligible flex slot like "W/R/T" / superflex "Q/W/R/T") and a
        `count`; `settings.stat_modifiers` is a list of real per-stat
        scoring rules, each with a `name`/`display_name` (Yahoo's own
        scoring-category label, e.g. "Receptions"/"Rec" -- see
        help.yahoo.com's published scoring-category abbreviations) and a
        `value`. Matched by name/display_name rather than a hardcoded
        numeric stat_id: unlike ESPN's statId 53 (verified directly against
        a real espn_api League.settings.scoring_format), no Yahoo stat_id
        for receptions could be independently confirmed here, and guessing
        a numeric id that turns out wrong would silently read some other
        stat's value as points-per-reception -- matching the documented
        name is the honest, verifiable option.

        Returns the same {starters, bench, roster_size,
        points_per_reception} shape sleeper_service.parse_league_settings /
        espn_service_enhanced.get_scoring_and_roster_settings produce, so
        draft_assistant_service can treat all three platforms identically.
        Returns {"error": ...} on failure (missing/expired token, bad
        league_key, Yahoo outage) -- callers should fall back to generic
        behavior rather than fabricate real-looking numbers.
        """
        if not access_token:
            return {"error": "Not authenticated"}

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/settings"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            settings_data = data.get("fantasy_content", {}).get("league", {}).get("settings", {})
            if not isinstance(settings_data, dict):
                return {"error": "League settings unavailable"}

            # Yahoo's flex slot is commonly "W/R/T" (RB/WR/TE-eligible) or,
            # in a superflex league, "Q/W/R/T" (adds QB). A plain RB/WR/TE
            # flex is folded into the same "FLEX" key
            # draft_assistant_service._effective_position_requirements
            # already knows how to distribute across RB/WR/TE (mirroring
            # Sleeper's own "FLEX" slot label); a superflex slot that also
            # includes QB is kept under its own literal key instead of
            # being folded into RB/WR/TE, since doing so would understate
            # real QB need.
            letter_map = {"Q": "QB", "W": "WR", "R": "RB", "T": "TE"}

            starters: Dict[str, int] = {}
            bench = 0
            roster_size = 0
            raw_roster_positions = settings_data.get("roster_positions", {})
            if isinstance(raw_roster_positions, dict):
                for slot_key, slot_entry in raw_roster_positions.items():
                    if not (isinstance(slot_entry, dict) and "roster_position" in slot_entry):
                        continue
                    slot = slot_entry["roster_position"]
                    position = slot.get("position")
                    try:
                        count = int(slot.get("count") or 0)
                    except (TypeError, ValueError):
                        count = 0
                    if not position or count <= 0:
                        continue

                    roster_size += count

                    if position == "BN":
                        bench += count
                        continue
                    if position in ("IR", "IR+"):
                        # Real roster slots, but not real starting-lineup
                        # need for the positions this app tracks.
                        continue

                    if "/" in position:
                        eligible = {letter_map.get(p, p) for p in position.split("/") if p}
                        if eligible == {"RB", "WR", "TE"}:
                            starters["FLEX"] = starters.get("FLEX", 0) + count
                            continue
                        # e.g. superflex "Q/W/R/T" -- keep as its own
                        # literal slot rather than mis-folding QB need into
                        # RB/WR/TE.
                        starters[position] = starters.get(position, 0) + count
                        continue

                    starters[position] = starters.get(position, 0) + count

            points_per_reception = 0.0
            raw_stat_modifiers = settings_data.get("stat_modifiers", {})
            if isinstance(raw_stat_modifiers, dict):
                raw_stats = raw_stat_modifiers.get("stats", {})
                if isinstance(raw_stats, dict):
                    for stat_key, stat_entry in raw_stats.items():
                        if not (isinstance(stat_entry, dict) and "stat" in stat_entry):
                            continue
                        stat = stat_entry["stat"]
                        name = (stat.get("name") or "").strip().lower()
                        display_name = (stat.get("display_name") or "").strip().lower()
                        if name == "receptions" or display_name == "rec":
                            try:
                                points_per_reception = float(stat.get("value") or 0.0)
                            except (TypeError, ValueError):
                                points_per_reception = 0.0
                            break

            if not starters and not bench:
                return {"error": "League settings unavailable"}

            return {
                "starters": starters,
                "bench": bench,
                "roster_size": roster_size,
                "points_per_reception": points_per_reception,
                "source": "yahoo",
            }
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Failed to get league settings: {self._error_detail(e)}"}
        except Exception as e:
            return {"error": f"Failed to parse league settings: {str(e)}"}

    async def get_league_teams(self, access_token: str, league_key: str) -> List[Dict[str, Any]]:
        """Get all teams in Yahoo league"""
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/teams"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get teams: {self._error_detail(e)}"}]

    async def get_team_roster(self, access_token: str, team_key: str, week: int = None) -> Dict[str, Any]:
        """Get roster for specific Yahoo team"""
        if not access_token:
            return {"error": "Not authenticated"}

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/team/{team_key}/roster"

            if week:
                url += f";week={week}"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Failed to get roster: {self._error_detail(e)}"}

    async def get_available_players(self, access_token: str, league_key: str, position: str = None, count: int = 25) -> List[Dict[str, Any]]:
        """Get available players in Yahoo league"""
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/players"

            params = {
                "format": "json",
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get available players: {self._error_detail(e)}"}]

    async def get_draft_results(self, access_token: str, league_key: str) -> List[Dict[str, Any]]:
        """Get draft results from Yahoo league"""
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/draftresults"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get draft results: {self._error_detail(e)}"}]

    async def monitor_live_draft(self, access_token: str, league_key: str) -> Dict[str, Any]:
        """Monitor live draft progress"""
        if not access_token:
            return {"error": "Not authenticated"}

        try:
            # Get league info to check draft status
            league_info = await self.get_league_info(access_token, league_key)

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
                draft_results = await self.get_draft_results(access_token, league_key)
                return {
                    "status": "completed",
                    "draft_results": draft_results
                }
            else:
                # Draft in progress - get current available players
                available_players = await self.get_available_players(access_token, league_key, count=50)
                recent_picks = await self.get_draft_results(access_token, league_key)

                return {
                    "status": "in_progress",
                    "available_players": available_players[:20],
                    "recent_picks": recent_picks[-10:] if recent_picks else [],
                    "league_info": league_info
                }
        except Exception as e:
            return {"error": f"Failed to monitor draft: {str(e)}"}

    async def get_matchups(self, access_token: str, league_key: str, week: int) -> List[Dict[str, Any]]:
        """Get matchups for specific week"""
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/scoreboard;week={week}"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get matchups: {self._error_detail(e)}"}]

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


yahoo_service = YahooFantasyService()
