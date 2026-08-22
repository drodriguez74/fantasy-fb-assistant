from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime
from app.services.ai_service import ai_service
from app.services.sleeper_service import sleeper_service
from app.services.espn_service_enhanced import espn_service_enhanced
from app.services.yahoo_service import yahoo_service
from enum import Enum
import json


class DraftPlatform(Enum):
    SLEEPER = "sleeper"
    ESPN = "espn"
    YAHOO = "yahoo"


class DraftAssistantService:
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
            
            # Calculate positional needs
            needs_analysis = await self._calculate_positional_needs(
                position_counts, total_picks, draft_settings
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

    async def _get_sleeper_draft_state(self, league_id: str) -> Dict[str, Any]:
        """Get live draft state from Sleeper's real public API.

        Delegates to SleeperService.get_draft_state, which hits Sleeper's
        actual draft/league endpoints and computes available_players by
        diffing the full player pool against picks already made. That
        method's return shape (status, draft_id, current_pick, total_picks,
        available_players, trending_players, picks, draft_info, league_info)
        already lines up with what callers in this file expect, so this is a
        thin pass-through rather than a reshape.
        """
        try:
            return await sleeper_service.get_draft_state(league_id)
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
                }
                for player in raw_available
                if isinstance(player, dict) and "error" not in player
            ]

            picks = draft_info.get("picks", [])
            team_count = league_info.get("team_count") or 12
            roster_size = league_info.get("roster_settings", {}).get("roster_size", 16)

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
        
        return {
            "draft_progress": draft_progress,
            "current_round": current_round,
            "position_counts": position_counts,
            "position_needs": self._get_position_needs(position_counts, current_round),
            "strategy_recommendation": strategy,
            "urgency_positions": self._get_urgency_positions(position_counts, current_round)
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
            
            # Generate recommendations using AI service
            recommendations = await ai_service.generate_draft_recommendation(
                available_players=available_players[:15],
                team_needs=draft_analysis.get("position_needs", []),
                draft_position=draft_analysis.get("current_round", 1),
                scoring_format=context["scoring_format"]
            )
            
            return recommendations
            
        except Exception as e:
            return {"error": f"AI recommendation failed: {str(e)}", "recommendations": []}

    async def _calculate_player_values(self, 
                                      available_players: List[Dict[str, Any]], 
                                      draft_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate player values and identify sleepers"""
        value_picks = []
        sleepers = []
        
        for player in available_players:
            # Simple value calculation (can be enhanced)
            projected_points = player.get("projected_points", 0)
            ownership = player.get("ownership", 100)
            
            # Value pick: high projected points, lower ownership
            value_score = projected_points * (100 - ownership) / 100
            
            if value_score > 15:  # Threshold for value
                value_picks.append({
                    "player": player,
                    "value_score": value_score,
                    "reason": f"High projection ({projected_points:.1f}) with low ownership ({ownership:.1f}%)"
                })
            
            # Sleeper: lower ownership but decent upside
            if ownership < 20 and projected_points > 8:
                sleepers.append({
                    "player": player,
                    "sleeper_score": projected_points / ownership if ownership > 0 else projected_points,
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

    def _get_position_needs(self, position_counts: Dict[str, int], round_num: int) -> List[str]:
        """Determine positional needs based on roster construction"""
        needs = []
        
        # Standard needs based on round
        if position_counts.get("RB", 0) < 2 and round_num <= 8:
            needs.append("RB")
        if position_counts.get("WR", 0) < 2 and round_num <= 8:
            needs.append("WR")
        if position_counts.get("QB", 0) == 0 and round_num >= 4:
            needs.append("QB")
        if position_counts.get("TE", 0) == 0 and round_num >= 6:
            needs.append("TE")
        if position_counts.get("K", 0) == 0 and round_num >= 12:
            needs.append("K")
        if position_counts.get("DEF", 0) == 0 and round_num >= 12:
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
                                         draft_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate detailed positional needs analysis"""
        # Standard roster requirements
        required_positions = {
            "QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1
        }
        
        needs = []
        for pos, required in required_positions.items():
            current = position_counts.get(pos, 0)
            if current < required:
                needs.append(pos)
        
        return {
            "top_needs": needs,
            "position_counts": position_counts,
            "recommended_targets": self._get_position_needs(position_counts, self._calculate_round(total_picks + 1))
        }

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