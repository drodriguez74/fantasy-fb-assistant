"""Client for FantasyPros' real public Consensus Rankings/ADP API.

FantasyPros is the industry-standard source for "expert consensus rankings"
(ECR) -- ranks aggregated across 130+ named experts -- and publishes a real,
documented REST API for it. This app's own ConsensusRankingService already
models its blending methodology on FantasyPros' published approach (see that
module's docstring); this service is the third real data source feeding it,
alongside Sleeper's search_rank and ESPN's percent_owned.

API details below were read directly from FantasyPros' own public OpenAPI
spec, not guessed:
  - Overview/pricing page: https://www.fantasypros.com/api-data/
  - Interactive docs (ReDoc, backed by the spec below):
    https://api.fantasypros.com/public/v2/docs
  - Raw OpenAPI 3.1 spec: https://api.fantasypros.com/public/v2/docs/fantasypros_v2_public.yml
    (openapi: 3.1.1, info.title: "FantasyPros Public API", version 2.0)

Base URL (spec `servers[0].url`): https://api.fantasypros.com/public/v2/json

Auth: `securitySchemes.api_key` in the spec is `{type: apiKey, name: x-api-key,
in: header}` -- every request needs an `x-api-key: <FANTASYPROS_API_KEY>`
header. There is no OAuth/bearer flow. Free tier ("$0/month, build/test/
prototype, all endpoints + sample data, generous daily call limit, non-
production use" per the pricing page) does not require payment info to get a
key, just a request via https://secure.fantasypros.com/api-keys/request/.

Endpoint used here -- `GET /{sport}/{season}/consensus-rankings` (spec line
~697), tagged "Rankings", described as "Returns detailed consensus player
rankings by ranking type and position":
  https://api.fantasypros.com/public/v2/json/nfl/{season}/consensus-rankings
    ?position=<NFLPositions>&scoring=<STD|PPR|HALF>&type=<NFLRankingTypes>
  NFLPositions (spec `components.schemas.NFLPositions`) includes ALL, QB, RB,
  WR, TE, K, DST, ... -- note "DST", not this app's "DEF".
  NFLRankingTypes (spec `components.schemas.NFLRankingTypes`) includes ADP,
  DRAFT, ROS, WW, etc. -- ADP is used here to match this feature's existing
  "consensus ADP" framing (see ConsensusRankingService's module docstring).
  NFLScoringTypes is STD/PPR/HALF -- PPR to match this app's PPR-only scope
  (see CLAUDE.md).

Response shape on success (200) is the spec's `NFLRankingsResponse` (an
`allOf` of the shared `ConsensusRankings` envelope + NFL-specific fields):
  {
    "sport": "NFL", "year": "2025", "week": "0",
    "count": 40, "total_experts": 25,
    "scoring": "PPR", "position_id": "RB", "ranking_type_name": "ADP",
    "players": [
      {
        "player_id": 19217, "player_name": "Jonathan Taylor",
        "player_team_id": "IND", "player_position_id": "RB",
        "player_positions": "RB", "pos_rank": "RB1",
        "rank_ecr": 1,                      # int|string per spec -- coerced below
        "player_bye_week": "14", "tier": 1,
        "player_owned_avg": 98.2, "player_owned_espn": 99.5,
        "player_owned_yahoo": 100, "player_yahoo_id": "32711",
        ...
      },
      ...
    ]
  }
On a documented error (e.g. 400 invalid position) the spec's error schema is
`{"message": "...", "parameter": "...", "valid_format": "..."}`.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.sleeper_service import sleeper_service

FANTASYPROS_BASE_URL = "https://api.fantasypros.com/public/v2/json"

# FantasyPros' NFLPositions enum uses "DST" for defense/special teams; this
# app's own position vocabulary (draft.py's positional-rankings, players.py)
# uses "DEF". Translate at this service's boundary rather than leaking
# FantasyPros' vocabulary into the rest of the app.
_POSITION_TO_FANTASYPROS = {"DEF": "DST"}


class FantasyProsService:
    def __init__(self):
        self.base_url = FANTASYPROS_BASE_URL
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def client(self) -> httpx.AsyncClient:
        # Same lazy/loop-aware pattern as SleeperService.client: a single
        # AsyncClient created eagerly binds its connection pool to whichever
        # event loop is running when it's first used, and reusing it from a
        # different loop later (e.g. successive TestClient requests) raises
        # "Event loop is closed". Recreate whenever the running loop changes.
        loop = asyncio.get_event_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = httpx.AsyncClient(timeout=10.0)
            self._client_loop = loop
        return self._client

    @property
    def is_configured(self) -> bool:
        """Whether a real FANTASYPROS_API_KEY is set. Mirrors ai_service.py
        only constructing its OpenAI/Anthropic clients when the matching key
        is present -- a missing key is an expected, normal condition (see
        .env.example), not an error to raise or crash on.
        """
        return bool(settings.FANTASYPROS_API_KEY)

    async def _current_season(self) -> int:
        """Real current NFL season, sourced from Sleeper's public /state/nfl
        endpoint (no credentials needed, already used the same way elsewhere
        in this codebase -- e.g. players.py's player-analysis endpoint).
        Falls back to today's calendar year if that call fails for any
        reason, rather than a hardcoded literal that goes stale every season.
        """
        nfl_state = await sleeper_service.get_nfl_state()
        if isinstance(nfl_state, dict) and "error" not in nfl_state:
            raw_season = nfl_state.get("season")
            if raw_season is not None:
                try:
                    return int(raw_season)
                except (TypeError, ValueError):
                    pass
        return datetime.now(timezone.utc).year

    async def get_consensus_rankings(
        self,
        position: str = "ALL",
        season: Optional[int] = None,
        scoring: str = "PPR",
        ranking_type: str = "ADP",
    ) -> Dict[str, Any]:
        """Fetch NFL consensus rankings/ADP from FantasyPros' real API.

        `season` defaults to the real current NFL season (via
        `_current_season`, above) when not given explicitly, rather than a
        hardcoded year that would silently go stale.

        Never raises: returns {"error": "..."} on a missing API key, a
        network failure, or a non-2xx response (e.g. the free tier's daily
        call limit), exactly like SleeperService's own methods -- callers
        (ConsensusRankingService via the get_consensus_rankings_players
        wrapper below) treat "no FantasyPros data" as a normal degrade case,
        not a failure to propagate.
        """
        if not self.is_configured:
            return {"error": "FANTASYPROS_API_KEY not configured"}

        if season is None:
            season = await self._current_season()

        fp_position = _POSITION_TO_FANTASYPROS.get(position.upper(), position.upper())

        try:
            response = await self.client.get(
                f"{self.base_url}/nfl/{season}/consensus-rankings",
                params={"position": fp_position, "scoring": scoring, "type": ranking_type},
                # Never log/print this header -- the api_key security scheme
                # is the only credential FantasyPros' API needs.
                headers={"x-api-key": settings.FANTASYPROS_API_KEY},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_consensus_rankings_players(
        self,
        position: str = "ALL",
        season: Optional[int] = None,
        scoring: str = "PPR",
        ranking_type: str = "ADP",
    ) -> List[Dict[str, Any]]:
        """Convenience wrapper for ConsensusRankingService: returns just the
        real `players` list from get_consensus_rankings, pre-normalized to a
        clean `{"player_name": str, "rank_ecr": float, ...}` shape.

        FantasyPros' own spec types `rank_ecr` as `[integer, string]`, not a
        guaranteed int -- coerced to float once here so the generic
        percentile-blending code in ConsensusRankingService can treat it
        exactly like Sleeper's search_rank (a plain, always-numeric field)
        instead of special-casing FantasyPros' raw-API quirk.

        Returns [] -- not an exception -- when no real FantasyPros data is
        available for any reason (no key configured, request failure,
        malformed response, or a player entry missing a name/rank). Callers
        should treat that identically to ESPN's "no session data" case: a
        clean degrade to whichever other sources are available, per
        ConsensusRankingService's existing single/two-source behavior.
        """
        data = await self.get_consensus_rankings(
            position=position, season=season, scoring=scoring, ranking_type=ranking_type
        )
        if not isinstance(data, dict) or "error" in data:
            return []

        players = data.get("players")
        if not isinstance(players, list):
            return []

        cleaned: List[Dict[str, Any]] = []
        for player in players:
            if not isinstance(player, dict):
                continue
            name = player.get("player_name")
            raw_rank = player.get("rank_ecr")
            if not name or raw_rank is None:
                continue
            try:
                rank_ecr = float(raw_rank)
            except (TypeError, ValueError):
                continue
            cleaned.append(
                {
                    "player_name": name,
                    "rank_ecr": rank_ecr,
                    "player_team_id": player.get("player_team_id"),
                    "pos_rank": player.get("pos_rank"),
                    "tier": player.get("tier"),
                }
            )
        return cleaned

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


fantasypros_service = FantasyProsService()
