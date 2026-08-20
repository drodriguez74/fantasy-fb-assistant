from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime
from app.services.ai_service import ai_service
from app.services.sleeper_service import sleeper_service
from app.services.espn_service import espn_service
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
                                  draft_settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """Initialize a real-time draft assistant session"""
        try:
            session_id = f"{platform.value}_{league_id}_{datetime.now().timestamp()}"
            
            # Get initial draft state based on platform
            if platform == DraftPlatform.SLEEPER:
                draft_state = await self._get_sleeper_draft_state(league_id)
            elif platform == DraftPlatform.ESPN:
                draft_state = await self._get_espn_draft_state(league_id)
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
            
            # Combine all recommendations
            recommendations = {
                "top_recommendations": ai_recommendations.get("recommendations", [])[:5],
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
        """Get draft state from Sleeper (demo mode with mock data)"""
        try:
            # For demo purposes, return mock draft state
            # In production, would call actual Sleeper API
            return {
                "status": "drafting",
                "draft_id": f"draft_{league_id}",
                "available_players": [],  # Will be populated from database
                "trending_players": [],
                "current_pick": 1,
                "total_picks": 192,  # 12 teams * 16 rounds
                "picks": [],
                "draft_info": {
                    "league_id": league_id,
                    "settings": {
                        "teams": 12,
                        "rounds": 16,
                        "pick_timer": 90
                    }
                },
                "league_info": {
                    "name": f"League {league_id}",
                    "season": "2024"
                }
            }
        except Exception as e:
            return {"error": str(e)}

    async def _get_espn_draft_state(self, league_id: str) -> Dict[str, Any]:
        """Get draft state from ESPN (demo mode)"""
        return {
            "status": "drafting",
            "draft_id": f"espn_draft_{league_id}",
            "available_players": [],
            "current_pick": 1,
            "total_picks": 192,
            "picks": [],
            "draft_info": {"league_id": league_id},
            "league_info": {"name": f"ESPN League {league_id}"}
        }
    
    async def _get_yahoo_draft_state(self, league_id: str) -> Dict[str, Any]:
        """Get draft state from Yahoo (demo mode)"""
        return {
            "status": "drafting", 
            "draft_id": f"yahoo_draft_{league_id}",
            "available_players": [],
            "current_pick": 1,
            "total_picks": 192,
            "picks": [],
            "draft_info": {"league_id": league_id},
            "league_info": {"name": f"Yahoo League {league_id}"}
        }

    async def _refresh_draft_state(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh draft state based on platform"""
        platform = session["platform"]
        league_id = session["league_id"]
        
        if platform == DraftPlatform.SLEEPER:
            return await self._get_sleeper_draft_state(league_id)
        elif platform == DraftPlatform.ESPN:
            return await self._get_espn_draft_state(league_id)
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