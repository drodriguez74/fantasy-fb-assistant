import httpx
from typing import Dict, List, Optional, Any
import asyncio
import logging
from datetime import datetime
import base64
import json
from app.core.config import settings
from app.services.scoring_rules import scoring_rules_from_yahoo

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

    @staticmethod
    def _flatten_resource(value: Any) -> Dict[str, Any]:
        """Yahoo's Fantasy API represents a singular resource (game, league,
        team, user, player, ...) as a single flat dict ONLY when nothing
        else was requested alongside it. As soon as a sub-resource is
        attached (e.g. a user's "games", a league's "settings"/"teams", a
        team's "roster"), Yahoo instead returns a LIST: one dict carrying
        the resource's own attributes, plus one further dict per attached
        sub-resource. Every parser in this file was written assuming a
        flat dict and 500'd with "'list' object has no attribute 'get'"
        the first time real (non-403'd) Yahoo data actually flowed through
        it -- confirmed live 2026-09-19 against a real connected league
        (`fantasy_content.users.0.user` == `[{"guid": ...}, {"games": {...}}]`).
        Known Yahoo API quirk -- the third-party `yfpy` library exists
        largely to paper over exactly this. Merging is a safe no-op for an
        already-flat dict.

        Not always a flat list of dicts, either: a `team` resource comes
        back as `[[{...}, {...}, [], {...}, ...]]` -- one outer element
        that is ITSELF a list of tiny single-key attribute dicts, with `[]`
        used as a placeholder for fields Yahoo didn't return. Confirmed
        live against a real `/league/{key}/teams` response. Recurse into
        any list element that is itself a list; silently skip anything
        that's neither a dict nor a list (e.g. that `[]` placeholder).
        """
        if isinstance(value, list):
            merged: Dict[str, Any] = {}
            for item in value:
                if isinstance(item, dict):
                    merged.update(item)
                elif isinstance(item, list):
                    merged.update(YahooFantasyService._flatten_resource(item))
            return merged
        return value if isinstance(value, dict) else {}

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
            user = self._flatten_resource(fantasy_content.get("users", {}).get("0", {}).get("user", {}))
            games = user.get("games", {})

            for game_key, game_data in games.items():
                if isinstance(game_data, dict) and "game" in game_data:
                    game = self._flatten_resource(game_data["game"])
                    if game.get("code") == "nfl" and str(season) in str(game.get("season", "")):
                        game_leagues = game.get("leagues", {})
                        for league_key, league_data in game_leagues.items():
                            if isinstance(league_data, dict) and "league" in league_data:
                                league = self._flatten_resource(league_data["league"])
                                leagues.append({
                                    "league_key": league.get("league_key"),
                                    "league_id": league.get("league_id"),
                                    "name": league.get("name"),
                                    "num_teams": league.get("num_teams"),
                                    "scoring_type": league.get("scoring_type"),
                                    "league_type": league.get("league_type"),
                                })

            return leagues
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            detail = self._error_detail(e)
            # On failure, probe a ladder of progressively-simpler Fantasy
            # endpoints and log which (if any) the token can actually reach.
            # This pins down whether it's a whitelist block (nothing works,
            # not even the public /game/nfl with a bearer token) or just this
            # one collection path being fussy (simpler calls succeed).
            await self._probe_fantasy_access(access_token)
            return [{"error": f"Failed to get leagues: {detail}"}]

    async def get_current_user_teams(self, access_token: str, season: int = 2024) -> List[Dict[str, Any]]:
        """Real "which team is mine, per league" -- no guessing/matching.

        Yahoo's per-manager `guid` field is NOT usable for this: it comes
        back as the literal masked string "--hidden--" for every manager
        in a league's team list, confirmed live to include the
        requester's own. The actual real signal Yahoo exposes is the
        `is_owned_by_current_login` flag on a team resource, surfaced by
        querying teams under the authenticated user
        (`/users;use_login=1/.../teams`, server-side scoped to that user)
        rather than a league's full team list. Confirmed live 2026-09-22.

        Returns one entry per real team the user owns across their NFL
        leagues this season: {league_key, team_key, team_id, team_name}.
        """
        if not access_token:
            return [{"error": "Not authenticated"}]

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/users;use_login=1/games;game_keys=nfl/teams"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            my_teams = []
            fantasy_content = data.get("fantasy_content", {})
            user = self._flatten_resource(fantasy_content.get("users", {}).get("0", {}).get("user", {}))
            games = user.get("games", {})

            for game_key, game_data in games.items():
                if isinstance(game_data, dict) and "game" in game_data:
                    game = self._flatten_resource(game_data["game"])
                    if game.get("code") == "nfl" and str(season) in str(game.get("season", "")):
                        game_teams = game.get("teams", {})
                        for team_key, team_data in game_teams.items():
                            if isinstance(team_data, dict) and "team" in team_data:
                                team = self._flatten_resource(team_data["team"])
                                team_key_full = team.get("team_key") or ""
                                # team_key is "{league_key}.t.{team_id}" --
                                # derive the owning league_key by stripping
                                # the ".t.N" suffix rather than a second
                                # round trip to look it up.
                                league_key = (
                                    team_key_full.rsplit(".t.", 1)[0] if ".t." in team_key_full else None
                                )
                                my_teams.append({
                                    "league_key": league_key,
                                    "team_key": team_key_full,
                                    "team_id": team.get("team_id"),
                                    "team_name": team.get("name"),
                                })

            return my_teams
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get your teams: {self._error_detail(e)}"}]

    async def _probe_fantasy_access(self, access_token: str) -> None:
        """Diagnostic: hit several Fantasy API endpoints and log status for
        each. Purely for debugging the 403 'not authorized' situation --
        never raises, never returned to the caller."""
        headers = {"Authorization": f"Bearer {access_token}"}
        probes = [
            "/game/nfl",
            "/users;use_login=1/games;game_keys=nfl",
            "/users;use_login=1/games/leagues",
            "/users;use_login=1/games;game_keys=nfl/leagues",
        ]
        for path in probes:
            try:
                r = await self.client.get(
                    f"{self.base_url}{path}", headers=headers, params={"format": "json"}
                )
                body = r.text.strip()[:200]
                logger.warning(f"Yahoo probe {r.status_code} {path} :: {body}")
            except Exception as ex:  # noqa: BLE001 - diagnostic only
                logger.warning(f"Yahoo probe ERROR {path} :: {ex}")

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

            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))

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

        Real shapes, confirmed live 2026-09-23 against a real connected
        league's /league/{key}/settings response (the first time this
        method was ever checked against actual data rather than
        third-party wrapper docs -- it was silently broken before this):
        `settings.roster_positions` is a real PLAIN LIST of
        `{"roster_position": {"position": ..., "count": ...}}` entries
        (NOT the "0"/"1"/"count"-keyed collection style games/leagues/
        teams/players use elsewhere in this file); `settings.
        stat_modifiers.stats` is likewise a real plain list, but each
        entry carries only `stat_id`/`value` -- no name/display_name at
        all, despite this docstring previously claiming otherwise (that
        claim was never actually verified against live data). Real names
        come from a DIFFERENT sibling collection on this same response,
        `settings.stat_categories.stats` (also a plain list), which is
        where scoring_rules.YAHOO_STAT_ID_MAP's stat_id -> name mapping
        was confirmed against -- see that module for the full canonical
        cross-platform scoring_rules this method now also returns.

        Returns the same {starters, bench, roster_size,
        points_per_reception} shape sleeper_service.parse_league_settings /
        espn_service_enhanced.get_scoring_and_roster_settings produce
        (plus a `scoring_rules` key, matching ESPN's), so
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

            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            settings_data = self._flatten_resource(league_data.get("settings", {}))
            if not settings_data:
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
            # A real plain list, not the "0"/"count"-keyed collection
            # style -- confirmed live (see this method's docstring).
            raw_roster_positions = settings_data.get("roster_positions", [])
            if isinstance(raw_roster_positions, list):
                for slot_entry in raw_roster_positions:
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

            # Also a real plain list (settings_data["stat_modifiers"] is a
            # dict with one "stats" key whose value is the list) -- each
            # entry only carries stat_id/value, matched against the
            # confirmed real id map in scoring_rules.py.
            stat_modifiers_container = settings_data.get("stat_modifiers", {})
            raw_stats = (
                stat_modifiers_container.get("stats", [])
                if isinstance(stat_modifiers_container, dict)
                else []
            )
            flat_stats = [
                entry["stat"] for entry in raw_stats
                if isinstance(entry, dict) and isinstance(entry.get("stat"), dict)
            ] if isinstance(raw_stats, list) else []

            scoring_rules = scoring_rules_from_yahoo(flat_stats)
            # Receptions is stat_id 11 (see scoring_rules.YAHOO_STAT_ID_MAP,
            # confirmed live) -- read the same already-built canonical
            # rules dict rather than re-scanning flat_stats a second time.
            points_per_reception = scoring_rules.get("receiving", {}).get("reception", 0.0)
            # Every scored stat's raw value by Yahoo stat_id, including the
            # ones the canonical rules don't model (first downs, 40+ yard
            # plays, pick-sixes...) -- weekly_projections scores those too.
            stat_values: Dict[int, float] = {}
            for stat in flat_stats:
                try:
                    stat_values[int(stat.get("stat_id"))] = float(stat.get("value"))
                except (TypeError, ValueError):
                    continue

            if not starters and not bench:
                return {"error": "League settings unavailable"}

            # Real waiver system flag -- confirmed live: "0"/"1" (sometimes
            # a real bool depending on response) on this same settings
            # resource. Used by get_waiver_position below.
            uses_faab = settings_data.get("uses_faab")
            uses_faab = bool(int(uses_faab)) if isinstance(uses_faab, (int, str)) and str(uses_faab).strip() != "" else bool(uses_faab)

            return {
                "starters": starters,
                "bench": bench,
                "roster_size": roster_size,
                "points_per_reception": points_per_reception,
                "scoring_rules": scoring_rules,
                "stat_values": stat_values,
                "uses_faab": uses_faab,
                # Yahoo's own trade deadline ("YYYY-MM-DD"), when the league has one.
                "trade_end_date": settings_data.get("trade_end_date") or None,
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
            # Plain /teams only returns team metadata (name, key, waiver
            # priority, ...) -- no win/loss/points data at all. Yahoo's
            # "out" parameter attaches the "standings" sub-resource
            # (team_standings: outcome_totals + points_for/against) to
            # each team in the same call. Confirmed necessary live: without
            # it, every team came back with wins/losses/points_for/
            # points_against == null.
            url = f"{self.base_url}/league/{league_key}/teams;out=standings"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            teams = []
            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            teams_data = league_data.get("teams", {})

            for team_key, team_data in teams_data.items():
                if isinstance(team_data, dict) and "team" in team_data:
                    team = self._flatten_resource(team_data["team"])

                    # "managers" is a plain list (`[{"manager": {...}}]`),
                    # not the "0"/"count"-keyed collection style used
                    # elsewhere (games/leagues/teams) -- confirmed live.
                    # NOTE: manager.guid is NOT usable to identify "my
                    # team" -- Yahoo returns the literal masked string
                    # "--hidden--" for every manager's guid in this
                    # response, including (confirmed live) the requester's
                    # own. Use get_current_user_teams() instead, which
                    # relies on Yahoo's own real `is_owned_by_current_login`
                    # flag rather than guid-matching.
                    manager_nickname = None
                    managers_raw = team.get("managers")
                    if isinstance(managers_raw, list) and managers_raw:
                        first_manager = managers_raw[0]
                        if isinstance(first_manager, dict):
                            manager_nickname = first_manager.get("manager", {}).get("nickname")

                    team_standings = self._flatten_resource(team.get("team_standings", {}))
                    outcome_totals = team_standings.get("outcome_totals", {})

                    teams.append({
                        "team_key": team.get("team_key"),
                        "team_id": team.get("team_id"),
                        "name": team.get("name"),
                        "manager": manager_nickname,
                        "wins": outcome_totals.get("wins"),
                        "losses": outcome_totals.get("losses"),
                        "points_for": team_standings.get("points_for"),
                        "points_against": team_standings.get("points_against"),
                        # Real rolling-waiver claim order (1 = first
                        # priority) -- confirmed live on this same team
                        # resource. Meaningless for a FAAB league (Yahoo
                        # still returns it, but nobody uses it there).
                        "waiver_priority": team.get("waiver_priority"),
                    })

            return teams
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get teams: {self._error_detail(e)}"}]

    async def get_waiver_position(self, access_token: str, league_key: str, team_id: str) -> Dict[str, Any]:
        """This team's real standing to actually win a waiver claim --
        the Yahoo equivalent of espn_service_enhanced.get_waiver_position.

        Real for a rolling-priority Yahoo league (confirmed live
        2026-09-23): `settings.uses_faab` (real "0"/"1" flag) plus each
        team's real `waiver_priority` (1 = first claim priority),
        surfaced via get_league_settings/get_league_teams. NOT built for
        a FAAB Yahoo league -- this session's only real connected league
        uses rolling priority (`uses_faab: 0`), so no real FAAB
        budget/spend field name could be confirmed live the way
        `waiver_priority` was; guessing one and getting it wrong would
        silently show a fabricated-looking dollar amount, worse than an
        honest gap. Returns `{"error": ...}` for a FAAB league rather
        than a guessed number.
        """
        settings_data = await self.get_league_settings(access_token, league_key)
        teams = await self.get_league_teams(access_token, league_key)
        if isinstance(teams, list) and teams and isinstance(teams[0], dict) and "error" in teams[0]:
            return {"error": teams[0]["error"]}

        target_team = next((t for t in teams if str(t.get("team_id")) == str(team_id)), None)
        if not target_team:
            return {"error": f"Team {team_id} not found in league"}

        uses_faab = settings_data.get("uses_faab") if "error" not in settings_data else None
        if uses_faab:
            return {
                "error": (
                    "This league uses Yahoo's FAAB waiver budget, which isn't "
                    "confirmed real for Yahoo in this app yet -- rolling waiver "
                    "priority is supported."
                )
            }

        return {
            "waiver_type": "priority",
            "total_teams": len(teams),
            "waiver_rank": target_team.get("waiver_priority"),
        }

    @staticmethod
    def build_team_key(league_key: Optional[str], team_id: Optional[str]) -> Optional[str]:
        """Yahoo team resources are addressed by the full `team_key`
        (`"{game}.l.{league}.t.{team_id}"`, e.g. `"470.l.652985.t.6"`), not
        the bare numeric `team_id` `UserLeague.team_id` stores -- several
        real call sites were passing the bare id straight to
        get_team_roster's `team_key` param and 400ing "Missing Resource"
        (confirmed live 2026-09-22, the first time a Yahoo `team_id` was
        ever real rather than always-null behind the earlier 403 block).
        Returns None if either input is missing, so callers degrade the
        same honest way a missing team_id already does everywhere else.
        """
        if not league_key or not team_id:
            return None
        return f"{league_key}.t.{team_id}"

    def _parse_roster_players(self, roster_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Players from one already-flattened `roster` resource -- shared by
        get_team_roster and get_league_rosters."""
        players: List[Dict[str, Any]] = []
        # The real player collection is nested one level deeper than it
        # looks -- `roster` carries its own attrs (coverage_type, week,
        # is_editable, ...) as direct keys, with the actual "players"
        # collection tucked under a numeric "0" sub-key alongside them
        # (Yahoo's per-coverage-instance indexing). Confirmed live
        # 2026-09-22 against a real roster response -- roster.get(
        # "players") directly was always empty.
        players_data = roster_data.get("0", {}).get("players", {})

        for player_key, player_data in players_data.items():
            if isinstance(player_data, dict) and "player" in player_data:
                player = self._flatten_resource(player_data["player"])
                # eligible_positions is a real list (`[{"position": "QB"}, ...]`,
                # can carry more than one for flex-eligible players) --
                # `primary_position` is Yahoo's own single real value
                # for "this player's position", confirmed present on
                # the same live response.
                selected_position = self._flatten_resource(player.get("selected_position", {}))
                # Real per-player bye week -- confirmed live
                # (`{"bye_weeks": {"week": "14"}}` on this same player
                # resource, same field _get_week_lineup already reads
                # for its on_bye flag).
                bye_weeks = self._flatten_resource(player.get("bye_weeks", {}))
                try:
                    bye_week = int(bye_weeks.get("week")) if bye_weeks.get("week") is not None else None
                except (TypeError, ValueError):
                    bye_week = None

                players.append({
                    "player_key": player.get("player_key"),
                    "player_id": player.get("player_id"),
                    "name": player.get("name", {}).get("full"),
                    "position": player.get("primary_position") or player.get("display_position"),
                    "team": player.get("editorial_team_abbr"),
                    "selected_position": selected_position.get("position"),
                    "status": player.get("status"),
                    "bye_week": bye_week,
                })

        return players

    async def get_league_rosters(self, access_token: str, league_key: str) -> List[Dict[str, Any]]:
        """Every team's current roster in one call (`/league/{key}/teams/
        roster`, confirmed live: all teams, same roster shape as
        get_team_roster). Returns [{team_id, team_key, team_name, players}],
        or [{"error": ...}] on failure."""
        if not access_token:
            return [{"error": "Not authenticated"}]
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/teams/roster"
            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get league rosters: {self._error_detail(e)}"}]

        league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
        teams_data = league_data.get("teams", {})
        teams: List[Dict[str, Any]] = []
        if isinstance(teams_data, dict):
            for key, entry in teams_data.items():
                if not (isinstance(entry, dict) and "team" in entry):
                    continue
                team = self._flatten_resource(entry["team"])
                roster_data = self._flatten_resource(team.get("roster", {}))
                teams.append({
                    "team_id": team.get("team_id"),
                    "team_key": team.get("team_key"),
                    "team_name": team.get("name"),
                    "players": self._parse_roster_players(roster_data),
                })
        return teams

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

            team_data_flat = self._flatten_resource(data.get("fantasy_content", {}).get("team", {}))
            roster_data = self._flatten_resource(team_data_flat.get("roster", {}))

            players = self._parse_roster_players(roster_data)

            return {
                "team_key": team_key,
                "week": week,
                "players": players
            }
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Failed to get roster: {self._error_detail(e)}"}

    async def get_bye_week_radar(self, access_token: str, league_key: str, team_key: str) -> Dict[str, Any]:
        """Real upcoming-bye-week list for one Yahoo team's roster -- the
        Yahoo equivalent of espn_service_enhanced.get_bye_week_radar.
        Real per-player `bye_week` now comes straight off get_team_roster
        (Yahoo's own `bye_weeks.week` field, confirmed live) -- no
        week-clamping bug to work around here the way ESPN's box_scores
        path had, since this doesn't go through a per-week box score at
        all.
        """
        if not access_token:
            return {"error": "Not authenticated"}

        roster_data = await self.get_team_roster(access_token, team_key)
        if "error" in roster_data:
            return roster_data

        league_info = await self.get_league_info(access_token, league_key)
        current_week = league_info.get("current_week") if "error" not in league_info else None
        try:
            current_week = int(current_week) if current_week is not None else 1
        except (TypeError, ValueError):
            current_week = 1

        team_name = None
        team_id = None
        teams = await self.get_league_teams(access_token, league_key)
        if isinstance(teams, list) and teams and not (isinstance(teams[0], dict) and "error" in teams[0]):
            my_team = next((t for t in teams if t.get("team_key") == team_key), None)
            if my_team:
                team_name = my_team.get("name")
                team_id = my_team.get("team_id")

        upcoming = []
        for player in roster_data.get("players", []):
            bye_week = player.get("bye_week")
            if not bye_week or bye_week < current_week:
                continue
            upcoming.append({
                "player_name": player.get("name"),
                "position": player.get("position"),
                "team": player.get("team"),
                "bye_week": bye_week,
                "weeks_until_bye": bye_week - current_week,
                "lineup_slot": player.get("selected_position"),
            })

        upcoming.sort(key=lambda p: p["weeks_until_bye"])

        return {
            "team_id": team_id,
            "team_name": team_name,
            "current_week": current_week,
            "upcoming_byes": upcoming,
        }

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
            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            players_data = league_data.get("players", {})

            for player_key, player_data in players_data.items():
                if isinstance(player_data, dict) and "player" in player_data:
                    player = self._flatten_resource(player_data["player"])
                    # eligible_positions is a real list (`[{"position": "QB"}, ...]`),
                    # not a dict -- same fix as get_team_roster's player
                    # parsing, confirmed against the same live shape.
                    percent_owned = self._flatten_resource(player.get("percent_owned", {}))
                    available_players.append({
                        "player_key": player.get("player_key"),
                        "player_id": player.get("player_id"),
                        "name": player.get("name", {}).get("full"),
                        "position": player.get("primary_position") or player.get("display_position"),
                        "team": player.get("editorial_team_abbr"),
                        "ownership_percentage": percent_owned.get("value"),
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
            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            results_data = league_data.get("draft_results", {})

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
            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            scoreboard = self._flatten_resource(league_data.get("scoreboard", {}))
            # The real matchups collection is nested under a numeric "0"
            # sub-key alongside scoreboard's own "week" attr -- same
            # coverage-instance-indexing quirk as roster["0"]["players"].
            # Confirmed live 2026-09-23 (this call previously always
            # returned []).
            matchups_data = scoreboard.get("0", {}).get("matchups", {})

            for matchup_key, matchup_data in matchups_data.items():
                if isinstance(matchup_data, dict) and "matchup" in matchup_data:
                    matchup = self._flatten_resource(matchup_data["matchup"])
                    # Real teams collection is likewise nested under "0",
                    # not a direct "teams" key on the matchup.
                    teams = matchup.get("0", {}).get("teams", {})

                    team1 = self._flatten_resource(teams.get("0", {}).get("team", {}))
                    team2 = self._flatten_resource(teams.get("1", {}).get("team", {}))
                    team1_points = self._flatten_resource(team1.get("team_points", {}))
                    team2_points = self._flatten_resource(team2.get("team_points", {}))

                    matchups.append({
                        "week": week,
                        "team1": {
                            "team_key": team1.get("team_key"),
                            "name": team1.get("name"),
                            "points": team1_points.get("total")
                        },
                        "team2": {
                            "team_key": team2.get("team_key"),
                            "name": team2.get("name"),
                            "points": team2_points.get("total")
                        }
                    })

            return matchups
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return [{"error": f"Failed to get matchups: {self._error_detail(e)}"}]

    async def get_week_matchup(
        self, access_token: str, league_key: str, team_key: str, week: int
    ) -> Dict[str, Any]:
        """Real weekly matchup for one Yahoo team -- the Yahoo equivalent of
        espn_service_enhanced.get_week_matchup, which this_week_service.py
        builds the "This Week" screen from. Matches its shape as closely
        as Yahoo's real API allows, with one real, confirmed gap: Yahoo's
        public API exposes real TEAM-level `team_projected_points` (its
        own server-computed weekly projection) and real `win_probability`
        per matchup, but genuinely no real PER-PLAYER projected points
        anywhere (checked live: `player_stats`/`player_points` sub-
        resources only ever carry real ACTUAL stats, never a projection;
        `;out=stats` on a roster 400s; confirmed 2026-09-23). Every
        player's `projected_points` here is honestly `None` --
        this_week_service.py's YAHOO branch must not run ESPN's
        points-only optimizer/start-sit logic against it, since an
        all-None-projection "optimization" would be meaningless, not
        real. `on_bye` IS real (Yahoo's own `bye_weeks.week` vs. the
        requested week); `pro_opponent` is honestly None -- not exposed
        on this resource.
        """
        if not access_token:
            return {"error": "Not authenticated"}

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/scoreboard;week={week}"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            scoreboard = self._flatten_resource(league_data.get("scoreboard", {}))
            matchups_data = scoreboard.get("0", {}).get("matchups", {})

            my_team_raw = None
            opp_team_raw = None
            for matchup_key, matchup_data in matchups_data.items():
                if not (isinstance(matchup_data, dict) and "matchup" in matchup_data):
                    continue
                matchup = self._flatten_resource(matchup_data["matchup"])
                teams = matchup.get("0", {}).get("teams", {})
                team_entries = [
                    self._flatten_resource(t.get("team", {}))
                    for t in teams.values()
                    if isinstance(t, dict) and "team" in t
                ]
                mine = next((t for t in team_entries if t.get("team_key") == team_key), None)
                if mine:
                    my_team_raw = mine
                    opp_team_raw = next((t for t in team_entries if t.get("team_key") != team_key), None)
                    break

            if not my_team_raw:
                return {"error": "No matchup found for this team this week"}

            def _team_summary(t: Optional[Dict[str, Any]]) -> Dict[str, Any]:
                if not t:
                    return {"team_id": None, "team_name": "Bye", "live_score": 0.0, "projected_score": 0.0}
                points = self._flatten_resource(t.get("team_points", {}))
                projected = self._flatten_resource(t.get("team_projected_points", {}))
                try:
                    live = round(float(points.get("total") or 0.0), 1)
                except (TypeError, ValueError):
                    live = 0.0
                try:
                    proj = round(float(projected.get("total") or 0.0), 1)
                except (TypeError, ValueError):
                    proj = 0.0
                return {
                    "team_id": t.get("team_id"),
                    "team_name": t.get("name"),
                    "live_score": live,
                    "projected_score": proj,
                }

            win_probability = my_team_raw.get("win_probability")
            try:
                win_probability = float(win_probability) if win_probability is not None else None
            except (TypeError, ValueError):
                win_probability = None

            my_lineup = await self._get_week_lineup(access_token, team_key, week)
            opponent_lineup = (
                await self._get_week_lineup(access_token, opp_team_raw["team_key"], week)
                if opp_team_raw and opp_team_raw.get("team_key")
                else []
            )

            return {
                "week": week,
                "my_team": _team_summary(my_team_raw),
                "opponent": _team_summary(opp_team_raw),
                "win_probability": win_probability,
                "my_lineup": my_lineup,
                "opponent_lineup": opponent_lineup,
            }
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Failed to get week matchup: {self._error_detail(e)}"}

    async def _get_week_lineup(self, access_token: str, team_key: str, week: int) -> List[Dict[str, Any]]:
        """Real per-player weekly lineup for one Yahoo team: real name/
        position/team/selected_position(slot)/status/actual points-so-far
        (player_points) and a real on_bye flag (bye_weeks.week == week).
        `projected_points` is honestly None -- see get_week_matchup's
        docstring for why. Never raises; a fetch failure degrades to an
        empty lineup (same best-effort pattern as this file's other
        internal helpers), since a missing lineup for one side shouldn't
        break the whole matchup view.
        """
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/team/{team_key}/roster;week={week}/players/stats"
            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return []

        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        team_data_flat = self._flatten_resource(data.get("fantasy_content", {}).get("team", {}))
        roster_data = self._flatten_resource(team_data_flat.get("roster", {}))
        players_data = roster_data.get("0", {}).get("players", {})

        lineup: List[Dict[str, Any]] = []
        for player_key, player_data in players_data.items():
            if not (isinstance(player_data, dict) and "player" in player_data):
                continue
            player = self._flatten_resource(player_data["player"])

            selected_position = self._flatten_resource(player.get("selected_position", {}))
            slot = (selected_position.get("position") or "").upper()

            player_points = self._flatten_resource(player.get("player_points", {}))
            try:
                points = round(float(player_points.get("total") or 0.0), 1)
            except (TypeError, ValueError):
                points = 0.0

            bye_weeks = self._flatten_resource(player.get("bye_weeks", {}))
            try:
                on_bye = str(bye_weeks.get("week")) == str(week)
            except Exception:  # noqa: BLE001 - defensive, never fabricate a bye
                on_bye = False

            eligible_positions = player.get("eligible_positions") or []
            eligible_slots = [
                e.get("position") for e in eligible_positions if isinstance(e, dict) and e.get("position")
            ]

            lineup.append({
                "player_id": player.get("player_id"),
                "name": player.get("name", {}).get("full"),
                "position": player.get("primary_position") or player.get("display_position"),
                "slot_position": slot,
                "team": player.get("editorial_team_abbr"),
                # Not exposed on this resource -- honestly omitted rather
                # than guessed.
                "pro_opponent": None,
                "injury_status": player.get("status") or "ACTIVE",
                # No real per-player projection exists in Yahoo's public
                # API -- see get_week_matchup's docstring. None (not 0),
                # so callers can tell "no data" apart from "real zero".
                "projected_points": None,
                "points": points,
                # Best-effort, derived from real signals only (never
                # fabricated): a nonzero real score means the game has
                # started/finished. A genuine 0-point game in progress or
                # already finished can't be told apart from "hasn't
                # played" this way -- an honest limitation, not a claim
                # of certainty.
                "game_played": 100 if points else 0,
                "on_bye": on_bye,
                "eligible_slots": eligible_slots,
            })

        return lineup

    async def get_team_matchup_history(
        self, access_token: str, league_key: str, team_key: str, through_week: int
    ) -> Dict[str, Any]:
        """This team's real result every week of the season so far -- the
        Yahoo equivalent of espn_service_enhanced.get_team_matchup_history.
        One real scoreboard call per week (real team-level `team_points`,
        Yahoo's own actual score once a week is played), same as that
        method's one-call-per-week pattern. Cheap early in the season,
        grows with it -- callers should cache this (see league_snapshots.py).
        """
        if not access_token:
            return {"error": "Not authenticated"}

        results: List[Dict[str, Any]] = []
        for week in range(1, through_week + 1):
            matchup = await self.get_week_matchup_summary(access_token, league_key, team_key, week)
            if matchup is None:
                continue

            my = matchup["my_team"]
            opp = matchup["opponent"]
            my_score = float(my.get("live_score") or 0.0)
            opp_score = float(opp.get("live_score") or 0.0)

            if opp.get("team_id") is None:
                result = "bye"
            elif week == through_week and my_score == 0.0 and opp_score == 0.0:
                # Not played yet -- same "no real score posted" signal
                # get_team_matchup_history uses for ESPN.
                result = "upcoming"
            elif my_score > opp_score:
                result = "win"
            elif my_score < opp_score:
                result = "loss"
            else:
                result = "tie"

            results.append({
                "week": week,
                "opponent_team_id": opp.get("team_id"),
                "opponent_name": opp.get("team_name") or "Bye",
                "my_score": round(my_score, 1),
                "opponent_score": round(opp_score, 1),
                "result": result,
            })

        return {"through_week": through_week, "matchups": results}

    async def get_week_matchup_summary(
        self, access_token: str, league_key: str, team_key: str, week: int
    ) -> Optional[Dict[str, Any]]:
        """Real team-level matchup summary for one week -- the shared core
        of get_week_matchup, without the (heavier) per-player lineup
        fetches get_team_matchup_history doesn't need. Returns None (not
        an error dict) when no matchup exists for this team/week (bye or
        bad input), so callers can just skip that week.
        """
        if not access_token:
            return None
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.base_url}/league/{league_key}/scoreboard;week={week}"

            response = await self.client.get(url, headers=headers, params={"format": "json"})
            response.raise_for_status()

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            league_data = self._flatten_resource(data.get("fantasy_content", {}).get("league", {}))
            scoreboard = self._flatten_resource(league_data.get("scoreboard", {}))
            matchups_data = scoreboard.get("0", {}).get("matchups", {})

            for matchup_key, matchup_data in matchups_data.items():
                if not (isinstance(matchup_data, dict) and "matchup" in matchup_data):
                    continue
                matchup = self._flatten_resource(matchup_data["matchup"])
                teams = matchup.get("0", {}).get("teams", {})
                team_entries = [
                    self._flatten_resource(t.get("team", {}))
                    for t in teams.values()
                    if isinstance(t, dict) and "team" in t
                ]
                mine = next((t for t in team_entries if t.get("team_key") == team_key), None)
                if not mine:
                    continue
                opp = next((t for t in team_entries if t.get("team_key") != team_key), None)

                def _summary(t: Optional[Dict[str, Any]]) -> Dict[str, Any]:
                    if not t:
                        return {"team_id": None, "team_name": "Bye", "live_score": 0.0}
                    points = self._flatten_resource(t.get("team_points", {}))
                    try:
                        live = round(float(points.get("total") or 0.0), 1)
                    except (TypeError, ValueError):
                        live = 0.0
                    return {"team_id": t.get("team_id"), "team_name": t.get("name"), "live_score": live}

                return {"my_team": _summary(mine), "opponent": _summary(opp)}

            return None
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


yahoo_service = YahooFantasyService()
