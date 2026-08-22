from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime
from app.services.ai_service import ai_service
from app.services.sleeper_service import sleeper_service
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from app.services.consensus_ranking_service import consensus_ranking_service
from app.services.fantasypros_service import fantasypros_service
from app.services.scoring_rules import calculate_points_from_stats, describe_scoring_rules
from enum import Enum
import json


class DraftPlatform(Enum):
    SLEEPER = "sleeper"
    ESPN = "espn"
    YAHOO = "yahoo"


class DraftAssistantService:
    # Positions a FLEX slot can be filled by. Real rosters don't
    # pre-assign FLEX to one position -- see _effective_position_requirements
    # for the heuristic used to fold FLEX slots into RB/WR/TE need.
    FLEX_ELIGIBLE_POSITIONS = ("RB", "WR", "TE")

    # Explicit fallback used only when no real, connected-league roster/
    # scoring settings could be fetched for a session -- e.g. Yahoo's
    # not-yet-implemented draft-state stub, or a real ESPN/Sleeper settings
    # call that itself errored. This is exactly what this file hardcoded
    # for every league before real per-league settings extraction existed;
    # kept as a named, honest fallback (see _get_league_settings) instead
    # of silently guessing at real numbers this session doesn't have.
    FALLBACK_ROSTER_REQUIREMENTS = {
        "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
        "bench": 6,
        "roster_size": 15,
        "points_per_reception": 0.0,  # implicit Standard scoring
        "source": "fallback_standard",
    }

    def __init__(self):
        self.active_drafts = {}  # Track active draft sessions
        self.position_tiers = {
            "QB": {"tier_1": 5, "tier_2": 8, "tier_3": 15},
            "RB": {"tier_1": 12, "tier_2": 24, "tier_3": 40},
            "WR": {"tier_1": 15, "tier_2": 30, "tier_3": 50},
            "TE": {"tier_1": 3, "tier_2": 8, "tier_3": 15},
            "K": {"tier_1": 5, "tier_2": 10, "tier_3": 20},
            "DEF": {"tier_1": 5, "tier_2": 10, "tier_3": 20}
        }

    async def start_draft_session(self,
                                  platform: DraftPlatform,
                                  league_id: str,
                                  user_team_id: str = None,
                                  draft_settings: Dict[str, Any] = None,
                                  platform_credentials: Dict[str, Any] = None) -> Dict[str, Any]:
        """Initialize a real-time draft assistant session

        platform_credentials carries whatever a platform needs to make
        authenticated calls on the caller's behalf -- for ESPN this is
        {"swid": ..., "espn_s2": ..., "season": ...} pulled from the
        caller's own UserLeague row (see live_draft.py's /start-session).
        It's stored on the session below so _refresh_draft_state can keep
        polling with the right credentials on every subsequent call, not
        just this first one. Never logged.
        """
        try:
            session_id = f"{platform.value}_{league_id}_{datetime.now().timestamp()}"

            # Get initial draft state based on platform
            if platform == DraftPlatform.SLEEPER:
                draft_state = await self._get_sleeper_draft_state(league_id)
            elif platform == DraftPlatform.ESPN:
                draft_state = await self._get_espn_draft_state(league_id, platform_credentials or {})
            elif platform == DraftPlatform.YAHOO:
                draft_state = await self._get_yahoo_draft_state(league_id)
            else:
                return {"error": "Unsupported platform"}

            if "error" in draft_state:
                return draft_state

            # Initialize session
            self.active_drafts[session_id] = {
                "platform": platform,
                "league_id": league_id,
                "user_team_id": user_team_id,
                "draft_settings": draft_settings or {},
                "platform_credentials": platform_credentials or {},
                "current_state": draft_state,
                "user_roster": [],
                "recommendations_history": [],
                "started_at": datetime.now(),
                "last_updated": datetime.now()
            }
            
            # Generate initial recommendations
            initial_recs = await self.get_live_recommendations(session_id)
            
            return {
                "session_id": session_id,
                "draft_state": draft_state,
                "initial_recommendations": initial_recs,
                "status": "active"
            }
            
        except Exception as e:
            return {"error": f"Failed to start draft session: {str(e)}"}

    async def get_live_recommendations(self, session_id: str) -> Dict[str, Any]:
        """Get real-time draft recommendations"""
        if session_id not in self.active_drafts:
            return {"error": "Draft session not found"}
        
        try:
            session = self.active_drafts[session_id]
            platform = session["platform"]
            
            # Refresh draft state
            updated_state = await self._refresh_draft_state(session)

            # Attach a real, inspectable consensus rank to every available
            # player before anything downstream (AI recommendations, value/
            # sleeper scoring, the draft board's tiering) consumes this
            # list -- see ConsensusRankingService for the blending method.
            # A Sleeper session only ever has Sleeper's own search_rank, so
            # this just reorders available_players by that signal's
            # percentile (same ordering Sleeper's raw rank would already
            # give). An ESPN session has that league's real percent_owned
            # for its available players *and* gets cross-referenced by name
            # against Sleeper's full player pool for a genuine two-source
            # consensus, not ESPN ownership alone.
            updated_state["available_players"] = await self._attach_consensus_ranks(
                platform, updated_state.get("available_players", [])
            )

            session["current_state"] = updated_state
            session["last_updated"] = datetime.now()
            
            # Analyze current draft situation
            draft_analysis = await self._analyze_draft_situation(session)
            
            # Get available players
            available_players = updated_state.get("available_players", [])
            
            # Generate AI recommendations
            ai_recommendations = await self._generate_ai_recommendations(
                session, available_players, draft_analysis
            )
            
            # Calculate value picks and sleepers
            value_analysis = await self._calculate_player_values(
                available_players, draft_analysis
            )
            
            # ai_service.generate_draft_recommendation returns flat
            # {player_name, position, reasoning, confidence} objects (see its
            # prompt template) rather than the {player: {...}, reason,
            # confidence, tier} shape the frontend renders. Reconcile each
            # recommended name against the real available_players pulled from
            # Sleeper so the UI gets a real player_id/team/projected_points
            # where we can find one, instead of crashing on a missing player.
            top_recommendations = self._enrich_ai_recommendations(
                ai_recommendations.get("recommendations", [])[:5],
                available_players,
                draft_analysis.get("current_round", 1)
            )

            # Combine all recommendations
            recommendations = {
                "top_recommendations": top_recommendations,
                "value_picks": value_analysis.get("value_picks", [])[:3],
                "sleeper_picks": value_analysis.get("sleepers", [])[:3],
                "position_needs": draft_analysis.get("position_needs", []),
                "draft_strategy": draft_analysis.get("strategy_recommendation", ""),
                "current_pick": updated_state.get("current_pick", 0),
                "time_remaining": updated_state.get("pick_time_remaining", 0),
                "confidence_score": ai_recommendations.get("confidence_score", 5)
            }
            
            # Store recommendations in history
            session["recommendations_history"].append({
                "pick_number": updated_state.get("current_pick", 0),
                "recommendations": recommendations,
                "timestamp": datetime.now()
            })
            
            return recommendations
            
        except Exception as e:
            return {"error": f"Failed to get recommendations: {str(e)}"}

    async def update_user_pick(self, session_id: str, player_picked: Dict[str, Any]) -> Dict[str, Any]:
        """Update draft session when user makes a pick"""
        if session_id not in self.active_drafts:
            return {"error": "Draft session not found"}
        
        try:
            session = self.active_drafts[session_id]
            
            # Add player to user's roster
            session["user_roster"].append({
                "player": player_picked,
                "pick_number": session["current_state"].get("current_pick", 0),
                "round": self._calculate_round(session["current_state"].get("current_pick", 0)),
                "timestamp": datetime.now()
            })
            
            # Get updated recommendations for next pick
            next_recommendations = await self.get_live_recommendations(session_id)
            
            return {
                "status": "pick_updated",
                "user_roster": session["user_roster"],
                "next_recommendations": next_recommendations
            }
            
        except Exception as e:
            return {"error": f"Failed to update pick: {str(e)}"}

    async def get_draft_board(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive draft board with tiers and rankings"""
        if session_id not in self.active_drafts:
            return {"error": "Draft session not found"}
        
        try:
            session = self.active_drafts[session_id]
            available_players = session["current_state"].get("available_players", [])
            
            # Organize players by position and tier
            draft_board = {}
            
            for position in ["QB", "RB", "WR", "TE", "K", "DEF"]:
                position_players = [p for p in available_players 
                                  if p.get("position") == position]
                
                # Sort by projected points or ranking
                position_players.sort(
                    key=lambda x: x.get("projected_points", 0), 
                    reverse=True
                )
                
                # Assign tiers
                tiers = self._assign_player_tiers(position_players, position)
                
                draft_board[position] = {
                    "players": position_players[:20],  # Top 20 per position
                    "tiers": tiers,
                    "available_count": len(position_players)
                }
            
            return {
                "draft_board": draft_board,
                "last_updated": datetime.now(),
                "total_available": len(available_players)
            }
            
        except Exception as e:
            return {"error": f"Failed to get draft board: {str(e)}"}

    async def get_team_analysis(self, session_id: str) -> Dict[str, Any]:
        """Analyze user's current team construction"""
        if session_id not in self.active_drafts:
            return {"error": "Draft session not found"}
        
        try:
            session = self.active_drafts[session_id]
            user_roster = session["user_roster"]
            draft_settings = session["draft_settings"]
            
            # Count positions
            position_counts = {}
            total_picks = len(user_roster)
            
            for pick in user_roster:
                pos = pick["player"].get("position", "UNKNOWN")
                position_counts[pos] = position_counts.get(pos, 0) + 1
            
            # Calculate positional needs, using the real connected league's
            # starter requirements when available (see _get_league_settings).
            needs_analysis = await self._calculate_positional_needs(
                position_counts, total_picks, draft_settings,
                self._get_league_settings(session)
            )
            
            # Analyze team strengths/weaknesses
            team_analysis = await ai_service.generate_player_analysis(
                player_name="Team Analysis",
                player_data={
                    "roster": user_roster,
                    "position_counts": position_counts,
                    "needs": needs_analysis
                }
            )
            
            return {
                "roster": user_roster,
                "position_counts": position_counts,
                "positional_needs": needs_analysis,
                "team_analysis": team_analysis,
                "roster_strength": self._calculate_roster_strength(user_roster),
                "next_pick_suggestions": needs_analysis.get("top_needs", [])[:3]
            }
            
        except Exception as e:
            return {"error": f"Failed to analyze team: {str(e)}"}

    async def _attach_consensus_ranks(
        self, platform: DraftPlatform, available_players: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Reorder/annotate `available_players` with a real consensus rank
        (see ConsensusRankingService). Sleeper sessions only ever carry
        Sleeper's own search_rank, so this degrades to a search_rank-based
        ordering. ESPN sessions carry that league's real percent_owned and
        are additionally cross-referenced by name against Sleeper's full
        player pool -- the same kind of get_all_players() call a Sleeper
        session's own _get_sleeper_draft_state already makes on every
        refresh, so this isn't a new request pattern, just made on ESPN's
        polling path too -- for a genuine two-source consensus. FantasyPros'
        real Consensus Rankings/ADP API (see fantasypros_service.py) is
        fetched here too, for every platform equally -- unlike ESPN's
        percent_owned, it isn't tied to any specific connected league, so
        there's no reason to gate it on `platform` the way the Sleeper
        cross-reference is.

        This is enrichment on top of the platform's own draft state, not a
        requirement for the rest of the pipeline: any failure here silently
        falls back to the unranked available_players list rather than
        breaking recommendations. FantasyPros' own call never raises (see
        fantasypros_service.get_consensus_rankings_players) and returns []
        when no FANTASYPROS_API_KEY is configured or the request fails,
        which is itself the degrade path back to Sleeper(+ESPN)-only.
        """
        if not available_players:
            return available_players

        try:
            other_source_players = None
            if platform == DraftPlatform.ESPN:
                all_sleeper = await sleeper_service.get_all_players()
                if isinstance(all_sleeper, dict) and "error" not in all_sleeper:
                    other_source_players = list(all_sleeper.values())

            fantasypros_players = await fantasypros_service.get_consensus_rankings_players(
                position="ALL", scoring="PPR", ranking_type="ADP"
            )

            return consensus_ranking_service.rank_players(
                available_players, other_source_players, fantasypros_players=fantasypros_players
            )
        except Exception:
            return available_players

    async def _get_sleeper_draft_state(self, league_id: str) -> Dict[str, Any]:
        """Get live draft state from Sleeper's real public API.

        Delegates to SleeperService.get_draft_state, which hits Sleeper's
        actual draft/league endpoints and computes available_players by
        diffing the full player pool against picks already made. That
        method's return shape (status, draft_id, current_pick, total_picks,
        available_players, trending_players, picks, draft_info, league_info)
        already lines up with what callers in this file expect, so this is
        mostly a thin pass-through -- the one addition is `league_settings`,
        the real per-league roster-slot/scoring shape derived from the same
        league_info this call already fetches (see
        sleeper_service.parse_league_settings). Roster-needs and
        value-scoring logic downstream (_get_league_settings,
        _effective_position_requirements, _calculate_player_values) reads
        that instead of the generic hardcoded requirements this file used
        to apply to every league regardless of what was actually connected.
        """
        try:
            state = await sleeper_service.get_draft_state(league_id)
            if "error" not in state:
                state["league_settings"] = sleeper_service.parse_league_settings(
                    state.get("league_info", {})
                )
            return state
        except Exception as e:
            return {"error": str(e)}

    async def _get_espn_draft_state(self, league_id: str, credentials: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get live draft state from ESPN's real API via espn_service_enhanced.

        Mirrors _get_sleeper_draft_state's contract (status, draft_id,
        current_pick, total_picks, available_players, trending_players,
        picks, draft_info, league_info) but sources it from espn_api instead
        of Sleeper's public API.

        ESPN's API needs per-user session cookies (swid/espn_s2) to read a
        private league; those are threaded in via `credentials`, which
        live_draft.py's /start-session populates from the caller's own
        UserLeague row (never from a file or any shared/global state), and
        which _refresh_draft_state re-passes on every subsequent poll so a
        long-running session keeps using that same user's credentials.
        Public leagues work fine with swid=None/espn_s2=None. If the league
        turns out to require auth and none was provided, espn_service_enhanced
        raises a clear error which is surfaced as-is below rather than
        papered over with empty/fake data.
        """
        credentials = credentials or {}
        swid = credentials.get("swid")
        espn_s2 = credentials.get("espn_s2")
        season = credentials.get("season", 2025)

        try:
            draft_info = await espn_service_enhanced.get_draft_info(
                league_id, season=season, swid=swid, espn_s2=espn_s2
            )
            if "error" in draft_info:
                return {"error": draft_info["error"]}

            league_info = await espn_service_enhanced.get_league_info(
                league_id, season=season, swid=swid, espn_s2=espn_s2
            )
            if "error" in league_info:
                return {"error": league_info["error"]}

            raw_available = await espn_service_enhanced.get_available_players(
                league_id, season=season, size=50, swid=swid, espn_s2=espn_s2
            )
            if isinstance(raw_available, list) and len(raw_available) > 0 and "error" in raw_available[0]:
                return {"error": raw_available[0]["error"]}
            if not isinstance(raw_available, list):
                raw_available = []

            # espn_service_enhanced's player formatter returns
            # {"name": ..., "percent_owned": ..., ...}; the recommendation/
            # value-pick logic below (_find_available_player,
            # _calculate_player_values) was built against Sleeper's
            # {"full_name": ..., "ownership": ..., ...} shape. Reshape here
            # rather than change the shared ESPN formatter that other,
            # already-working ESPN endpoints (roster, matchups, standings)
            # depend on as-is.
            available_players = [
                {
                    **player,
                    "full_name": player.get("name", "Unknown Player"),
                    "ownership": player.get("percent_owned", 0.0),
                    # Tags this record as ESPN-sourced so
                    # _calculate_player_values knows NOT to layer a raw-stat
                    # scoring-rules recalculation on top of `projected_points`
                    # here -- ESPN already computes that figure server-side
                    # using this league's real scoring settings (see that
                    # method's docstring), so recalculating from raw stats
                    # would double-count.
                    "platform": "espn",
                }
                for player in raw_available
                if isinstance(player, dict) and "error" not in player
            ]

            picks = draft_info.get("picks", [])
            team_count = league_info.get("team_count") or 12
            roster_size = league_info.get("roster_settings", {}).get("roster_size", 16)

            # Real per-league roster-slot (incl. FLEX/bench) and
            # points-per-reception settings, read directly off espn_api's
            # Settings object -- see get_scoring_and_roster_settings's
            # docstring for why get_league_info's own roster_settings block
            # above can't be trusted for this (its roster_size/
            # starting_lineup_size are always-16/9 fallback defaults, not
            # real data). Don't fail the whole draft session if this
            # particular call errors -- roster-needs/value-scoring logic
            # falls back to generic Standard-league behavior explicitly
            # (see DraftAssistantService.FALLBACK_ROSTER_REQUIREMENTS)
            # rather than blocking the live draft over it.
            league_settings = await espn_service_enhanced.get_scoring_and_roster_settings(
                league_id, season=season, swid=swid, espn_s2=espn_s2
            )
            if "error" in league_settings:
                league_settings = None

            return {
                "status": "complete" if draft_info.get("draft_completed") else "drafting",
                "draft_id": f"espn_{league_id}_{season}",
                "current_pick": len(picks) + 1,
                "total_picks": team_count * roster_size,
                "available_players": available_players[:50],
                # ESPN's API doesn't expose an "add trend" feed the way
                # Sleeper's does; leaving this empty is honest, not faked.
                "trending_players": [],
                "draft_info": draft_info,
                "picks": picks,
                "league_info": league_info,
                "league_settings": league_settings,
            }
        except Exception as e:
            return {"error": f"Failed to get ESPN draft state: {str(e)}"}

    async def _get_yahoo_draft_state(self, league_id: str) -> Dict[str, Any]:
        """STUB: Yahoo live draft state is not wired to real data yet.

        Real Yahoo live-draft polling needs a real OAuth access token via
        yahoo_service, which isn't configured in this environment. Rather
        than fabricate picks/available_players, this explicitly returns an
        empty/placeholder state. Wiring this up for real is legitimate
        follow-up scope, not done in this pass.
        """
        return {
            "status": "not_implemented",
            "draft_id": f"yahoo_draft_{league_id}",
            "available_players": [],
            "current_pick": 1,
            "total_picks": 192,
            "picks": [],
            "draft_info": {"league_id": league_id},
            "league_info": {"name": f"Yahoo League {league_id}"},
            "note": "Yahoo live draft polling is not implemented yet; this is placeholder data, not a real draft state."
        }

    async def _refresh_draft_state(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh draft state based on platform"""
        platform = session["platform"]
        league_id = session["league_id"]
        
        if platform == DraftPlatform.SLEEPER:
            return await self._get_sleeper_draft_state(league_id)
        elif platform == DraftPlatform.ESPN:
            return await self._get_espn_draft_state(league_id, session.get("platform_credentials", {}))
        elif platform == DraftPlatform.YAHOO:
            return await self._get_yahoo_draft_state(league_id)

        return session["current_state"]

    async def _analyze_draft_situation(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current draft situation and needs"""
        user_roster = session["user_roster"]
        current_pick = session["current_state"].get("current_pick", 1)
        total_picks = session["current_state"].get("total_picks", 192)
        
        # Calculate draft progress
        draft_progress = (current_pick / total_picks) * 100
        current_round = self._calculate_round(current_pick)
        
        # Analyze positional needs
        position_counts = {}
        for pick in user_roster:
            pos = pick["player"].get("position", "UNKNOWN")
            position_counts[pos] = position_counts.get(pos, 0) + 1
        
        # Determine strategy based on draft position and progress
        strategy = self._determine_draft_strategy(draft_progress, position_counts, current_round)

        # Real per-league roster-slot/scoring settings for this session
        # (or the explicit standard fallback -- see _get_league_settings),
        # threaded through draft_analysis so _generate_ai_recommendations
        # and _calculate_player_values don't need to re-derive it.
        league_settings = self._get_league_settings(session)

        return {
            "draft_progress": draft_progress,
            "current_round": current_round,
            "position_counts": position_counts,
            "position_needs": self._get_position_needs(position_counts, current_round, league_settings),
            "strategy_recommendation": strategy,
            "urgency_positions": self._get_urgency_positions(position_counts, current_round),
            "league_settings": league_settings,
        }

    async def _generate_ai_recommendations(self, 
                                          session: Dict[str, Any], 
                                          available_players: List[Dict[str, Any]], 
                                          draft_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI-powered draft recommendations"""
        try:
            # Prepare context for AI
            context = {
                "user_roster": session["user_roster"],
                "available_players": available_players[:20],  # Top 20 available
                "draft_analysis": draft_analysis,
                "scoring_format": session["draft_settings"].get("scoring_format", "PPR")
            }

            league_settings = draft_analysis.get("league_settings") or self._get_league_settings(session)
            # Only pass a real numeric points_per_reception when we actually
            # have one for the connected league -- when we've fallen back to
            # FALLBACK_ROSTER_REQUIREMENTS (no real settings available), let
            # generate_draft_recommendation use its own scoring_format-label
            # fallback instead of asserting "0 points per reception" as if
            # it were confirmed real data for this league.
            points_per_reception = (
                league_settings.get("points_per_reception")
                if league_settings.get("source") != "fallback_standard"
                else None
            )
            # Same honesty rule as points_per_reception above: only pass the
            # real, connected-league scoring_rules dict when we actually
            # have one, never the fallback_standard placeholder as if it
            # were confirmed real data.
            scoring_rules = (
                league_settings.get("scoring_rules")
                if league_settings.get("source") != "fallback_standard"
                else None
            )

            # Generate recommendations using AI service
            recommendations = await ai_service.generate_draft_recommendation(
                available_players=available_players[:15],
                team_needs=draft_analysis.get("position_needs", []),
                draft_position=draft_analysis.get("current_round", 1),
                scoring_format=context["scoring_format"],
                points_per_reception=points_per_reception,
                scoring_rules=scoring_rules
            )

            return recommendations
            
        except Exception as e:
            return {"error": f"AI recommendation failed: {str(e)}", "recommendations": []}

    async def _calculate_player_values(self,
                                      available_players: List[Dict[str, Any]],
                                      draft_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate player values and identify sleepers.

        points_per_reception is the connected league's real per-reception
        scoring value (0.0 Standard, 0.5 Half-PPR, 1.0 full PPR, or any
        other league-specific override), threaded through via
        draft_analysis["league_settings"] (see _analyze_draft_situation ->
        _get_league_settings). A player's `projected_points` is adjusted by
        `receptions * points_per_reception` ONLY when the player record
        carries a real, not-yet-scored reception count under
        `projected_receptions` -- i.e. a raw stat count, not a number some
        platform already ran through its own scoring rules. The same
        raw-count-times-rate approach is generalized below to the rest of
        the league's real scoring rules (completions/incompletions/
        attempts, passing/rushing/receiving yards and TDs, interceptions,
        fumbles lost -- see app.services.scoring_rules) via a
        `projected_stat_breakdown` field, whenever a player record
        legitimately carries one.

        Neither platform this app currently reads available_players from
        reliably supplies raw per-stat ingredients today, for two different
        reasons -- both verified directly rather than assumed:
          - ESPN (espn_service_enhanced, via espn_api): a player's
            `projected_points` (sourced from `Player.projected_total_points`
            -- see espn_service_enhanced._format_player) is computed
            server-side by ESPN for the specific connected League object,
            using that league's own real scoring settings -- it already
            reflects real PPR/Half-PPR/Standard scoring AND every other
            real scoring category (completions, INTs, yardage, etc), not
            just receptions. Re-deriving any of that from raw stats here
            would double-count. This is exactly why ESPN player records
            built by _get_espn_draft_state are tagged `"platform": "espn"`
            -- the loop below explicitly skips the recalculation path for
            them, on top of the fact that they're deliberately NOT given a
            `projected_receptions`/`projected_stat_breakdown` field (ESPN's
            real per-stat raw projections DO exist, nested at
            `player["stats"][0]["projected_breakdown"]` --
            espn_api.football.player.Player.stats -- but are intentionally
            left there, unsurfaced at the top level, rather than wired into
            this recalculation and risking double-counting against
            `projected_total_points`).
          - Sleeper's public player-metadata endpoint (players/nfl -- the
            only one available_players is built from) carries no stats or
            projections at all: a real "Tyreek Hill" record pulled live
            from api.sleeper.app/v1/players/nfl has no points/receptions
            field whatsoever, only bio metadata (name/position/team/etc).
            There is nothing honest to adjust there yet -- for receptions
            or for any other category.

        This still applies the real adjustment whenever
        `projected_receptions` / `projected_stat_breakdown` genuinely is
        present on a non-ESPN player record, so it's correct today for any
        record shaped that way and forward-compatible if a platform's
        player enrichment adds real raw stats later -- rather than a no-op
        that quietly never fires regardless of what data eventually shows
        up.
        """
        league_settings = draft_analysis.get("league_settings") or {}
        points_per_reception = league_settings.get("points_per_reception") or 0.0
        scoring_rules = league_settings.get("scoring_rules")

        value_picks = []
        sleepers = []

        for player in available_players:
            # Simple value calculation (can be enhanced)
            projected_points = player.get("projected_points", 0) or 0
            ownership = player.get("ownership", 100)

            # Reception-scoring adjustment -- see docstring above for why
            # this is a no-op for both platforms' real data today, and why
            # that's the honest outcome rather than a bug.
            effective_points = projected_points
            receptions = player.get("projected_receptions")
            if points_per_reception and receptions:
                effective_points = projected_points + (receptions * points_per_reception)

            # Full scoring-rules recalculation (completions/incompletions,
            # attempts, INT, passing/rushing/receiving yards & TDs, fumbles
            # lost) -- fires only for a player record that (a) carries real
            # raw per-stat season projections under `projected_stat_breakdown`
            # and (b) is NOT an ESPN record, since ESPN's own
            # `projected_points` already legitimately reflects the league's
            # complete real scoring rules (see docstring). Replaces, rather
            # than adds to, `effective_points` -- the raw breakdown is a
            # full per-stat picture, not an incremental adjustment like the
            # reception-only case above.
            raw_stat_breakdown = player.get("projected_stat_breakdown")
            if scoring_rules and raw_stat_breakdown and player.get("platform") != "espn":
                effective_points = calculate_points_from_stats(raw_stat_breakdown, scoring_rules)

            # Value pick: high projected points, lower ownership
            value_score = effective_points * (100 - ownership) / 100

            if value_score > 15:  # Threshold for value
                value_picks.append({
                    "player": player,
                    "value_score": value_score,
                    "reason": f"High projection ({effective_points:.1f}) with low ownership ({ownership:.1f}%)"
                })

            # Sleeper: lower ownership but decent upside
            if ownership < 20 and effective_points > 8:
                sleepers.append({
                    "player": player,
                    "sleeper_score": effective_points / ownership if ownership > 0 else effective_points,
                    "reason": f"Low ownership sleeper with upside"
                })

        # Sort by scores
        value_picks.sort(key=lambda x: x["value_score"], reverse=True)
        sleepers.sort(key=lambda x: x["sleeper_score"], reverse=True)

        return {
            "value_picks": value_picks[:5],
            "sleepers": sleepers[:5]
        }

    def _enrich_ai_recommendations(self,
                                    raw_recommendations: List[Dict[str, Any]],
                                    available_players: List[Dict[str, Any]],
                                    current_round: int) -> List[Dict[str, Any]]:
        """Reshape AI-generated {player_name, position, reasoning, confidence}
        recommendations into {player, reason, confidence, tier} objects, and
        attach the real player record (player_id/team/projected_points) when
        we can match it by name against the live available_players list.
        """
        enriched = []
        # Simple round-based tier as a fallback when we can't derive a
        # position-ranked tier for an unmatched player.
        fallback_tier = min(4, ((max(current_round, 1) - 1) // 3) + 1)

        for rec in raw_recommendations:
            player_name = rec.get("player_name", "")
            matched = self._find_available_player(player_name, available_players)

            player = {
                "player_id": matched.get("player_id") if matched else player_name.lower().replace(" ", "_"),
                "full_name": matched.get("full_name") if matched else (player_name or "Unknown Player"),
                "position": (matched.get("position") if matched else None) or rec.get("position", ""),
                "team": matched.get("team") if matched else None,
                "projected_points": matched.get("projected_points") if matched else None,
            }

            enriched.append({
                "player": player,
                "reason": rec.get("reasoning", ""),
                "confidence": rec.get("confidence", 50),
                "tier": fallback_tier
            })

        return enriched

    def _find_available_player(self, player_name: str, available_players: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the real Sleeper player record matching an AI-recommended name."""
        if not player_name:
            return None

        target = player_name.strip().lower()
        if not target:
            return None

        for player in available_players:
            full_name = (player.get("full_name") or "").strip().lower()
            if full_name == target:
                return player

        # Fall back to a loose substring match in case the AI paraphrased
        # (e.g. suffixes like "Jr." or "II").
        for player in available_players:
            full_name = (player.get("full_name") or "").strip().lower()
            if full_name and (full_name in target or target in full_name):
                return player

        return None

    def _assign_player_tiers(self, players: List[Dict[str, Any]], position: str) -> Dict[str, List]:
        """Assign players to tiers based on position"""
        tiers = {"tier_1": [], "tier_2": [], "tier_3": [], "tier_4": []}
        
        tier_limits = self.position_tiers.get(position, {"tier_1": 5, "tier_2": 10, "tier_3": 20})
        
        for i, player in enumerate(players):
            if i < tier_limits["tier_1"]:
                tiers["tier_1"].append(player)
            elif i < tier_limits["tier_2"]:
                tiers["tier_2"].append(player)
            elif i < tier_limits["tier_3"]:
                tiers["tier_3"].append(player)
            else:
                tiers["tier_4"].append(player)
        
        return tiers

    def _calculate_round(self, pick_number: int, teams: int = 12) -> int:
        """Calculate round number from pick number"""
        return ((pick_number - 1) // teams) + 1

    def _determine_draft_strategy(self, progress: float, position_counts: Dict[str, int], round_num: int) -> str:
        """Determine recommended draft strategy"""
        if round_num <= 3:
            return "Focus on elite RBs and WRs - build your foundation with proven studs"
        elif round_num <= 6:
            if position_counts.get("QB", 0) == 0:
                return "Consider QB if tier 1 available, otherwise continue RB/WR depth"
            else:
                return "Build RB/WR depth and consider elite TE"
        elif round_num <= 10:
            return "Fill positional needs and target high-upside players"
        else:
            return "Handcuffs, lottery tickets, and streaming options"

    def _get_position_needs(self, position_counts: Dict[str, int], round_num: int,
                             league_settings: Optional[Dict[str, Any]] = None) -> List[str]:
        """Determine positional needs based on roster construction.

        Needs are gated by draft-round pacing (e.g. don't flag K/DEF as a
        need in round 3, even though the roster technically has 0 of them)
        so early picks aren't skewed toward end-of-roster positions. The
        per-position target count used for that comparison comes from the
        connected league's real starter requirements -- including FLEX
        slots folded into whichever of RB/WR/TE is thinnest, see
        _effective_position_requirements -- when league_settings is
        available; otherwise it falls back to the same generic
        RB2/WR2/QB1/TE1/K1/DEF1 shape this file always used (no connected
        league, Yahoo's stub, or a failed settings fetch -- see
        FALLBACK_ROSTER_REQUIREMENTS).

        reqs.get(pos, 0) defaults to 0, not some generic non-zero count:
        _effective_position_requirements is always given either real
        settings or FALLBACK_ROSTER_REQUIREMENTS (never nothing), so a
        position missing from reqs means the connected league genuinely
        doesn't roster it (e.g. a no-kicker league) -- that's real
        information, not a gap to paper over with a guessed default.
        """
        reqs = self._effective_position_requirements(
            position_counts, league_settings or self.FALLBACK_ROSTER_REQUIREMENTS
        )

        needs = []

        if position_counts.get("RB", 0) < reqs.get("RB", 0) and round_num <= 8:
            needs.append("RB")
        if position_counts.get("WR", 0) < reqs.get("WR", 0) and round_num <= 8:
            needs.append("WR")
        if position_counts.get("QB", 0) < reqs.get("QB", 0) and round_num >= 4:
            needs.append("QB")
        if position_counts.get("TE", 0) < reqs.get("TE", 0) and round_num >= 6:
            needs.append("TE")
        if position_counts.get("K", 0) < reqs.get("K", 0) and round_num >= 12:
            needs.append("K")
        if position_counts.get("DEF", 0) < reqs.get("DEF", 0) and round_num >= 12:
            needs.append("DEF")

        return needs

    def _get_urgency_positions(self, position_counts: Dict[str, int], round_num: int) -> List[str]:
        """Get positions that need to be filled urgently"""
        urgent = []
        
        if round_num >= 10:
            if position_counts.get("QB", 0) == 0:
                urgent.append("QB")
            if position_counts.get("TE", 0) == 0:
                urgent.append("TE")
        
        if round_num >= 14:
            if position_counts.get("K", 0) == 0:
                urgent.append("K")
            if position_counts.get("DEF", 0) == 0:
                urgent.append("DEF")
        
        return urgent

    async def _calculate_positional_needs(self,
                                         position_counts: Dict[str, int],
                                         total_picks: int,
                                         draft_settings: Dict[str, Any],
                                         league_settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate detailed positional needs analysis using the connected
        league's real starter requirements (QB/RB/WR/TE/FLEX/K/DEF slot
        counts, with FLEX folded into whichever of RB/WR/TE is thinnest --
        see _effective_position_requirements) instead of one hardcoded
        QB1/RB2/WR2/TE1/K1/DEF1 shape applied to every league regardless of
        what's actually connected. Falls back to that same generic shape
        (FALLBACK_ROSTER_REQUIREMENTS) when no real settings were available
        for this session, e.g. get_team_analysis calling this without a
        connected league.
        """
        league_settings = league_settings or self.FALLBACK_ROSTER_REQUIREMENTS
        required_positions = self._effective_position_requirements(position_counts, league_settings)

        needs = []
        for pos, required in required_positions.items():
            current = position_counts.get(pos, 0)
            if current < required:
                needs.append(pos)

        return {
            "top_needs": needs,
            "position_counts": position_counts,
            "recommended_targets": self._get_position_needs(
                position_counts, self._calculate_round(total_picks + 1), league_settings
            )
        }

    def _get_league_settings(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Real roster-slot/scoring settings for this session's connected
        league (see _get_sleeper_draft_state / _get_espn_draft_state,
        which attach a "league_settings" key derived from the real
        platform data they fetch), or the explicit standard-league
        fallback (FALLBACK_ROSTER_REQUIREMENTS) when none could be
        fetched -- e.g. Yahoo's still-a-stub draft state, or a real
        ESPN/Sleeper settings call that itself errored. Never silently
        fabricates real-looking numbers; the fallback is the exact same
        generic shape this file always used before real per-league
        settings extraction existed.
        """
        settings = session.get("current_state", {}).get("league_settings")
        if not settings or "error" in settings or not settings.get("starters"):
            return self.FALLBACK_ROSTER_REQUIREMENTS
        return settings

    def _effective_position_requirements(self, position_counts: Dict[str, int],
                                          league_settings: Dict[str, Any]) -> Dict[str, int]:
        """Real per-position starter requirement for the connected league,
        with FLEX slots folded into whichever of RB/WR/TE currently has the
        largest shortfall against what's been drafted so far -- i.e. each
        FLEX slot counts toward whichever position is thinnest at the time
        it's considered, rather than being ignored or split evenly across
        all three regardless of actual roster construction. This is a
        simplification (real lineups don't pre-assign a FLEX slot to one
        position), but it's an explicit, documented heuristic, not a
        fabrication -- and it only affects RB/WR/TE; every other real
        starter requirement (QB/K/DEF/any other slot the league carries)
        passes through unchanged.
        """
        starters = dict(league_settings.get("starters", {}) or {})
        flex_count = starters.pop("FLEX", 0)

        flex_eligible_requirements = {
            pos: starters.get(pos, 0) for pos in self.FLEX_ELIGIBLE_POSITIONS
        }
        for _ in range(flex_count):
            thinnest = max(
                self.FLEX_ELIGIBLE_POSITIONS,
                key=lambda pos: flex_eligible_requirements[pos] - position_counts.get(pos, 0)
            )
            flex_eligible_requirements[thinnest] += 1

        merged = dict(starters)
        merged.update(flex_eligible_requirements)
        return merged

    def _calculate_roster_strength(self, roster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall roster strength"""
        if not roster:
            return {"score": 0, "grade": "N/A"}
        
        total_projected = sum(pick["player"].get("projected_points", 0) for pick in roster)
        avg_projected = total_projected / len(roster)
        
        # Simple grading scale
        if avg_projected >= 15:
            grade = "A"
        elif avg_projected >= 12:
            grade = "B"
        elif avg_projected >= 10:
            grade = "C"
        else:
            grade = "D"
        
        return {
            "score": round(avg_projected, 1),
            "grade": grade,
            "total_projected": round(total_projected, 1),
            "picks_made": len(roster)
        }


draft_assistant = DraftAssistantService()