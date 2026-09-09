"""
Post-Draft Analysis Service

Provides comprehensive roster evaluation and personalized waiver wire recommendations
after completing a fantasy football draft.
"""

import re
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func

from app.models.player import Player, Position
from app.models.draft_session import DraftSession
from app.models.historical_performance import PlayerHistoricalPerformance
from app.models.waiver_wire import WaiverWireRecommendation
from app.services.waiver_wire_service import WaiverWireService
from app.services.sleeper_service import SleeperService
from app.services.scoring_calculation_service import ScoringCalculationService
from app.services.matchup_analysis_service import MatchupAnalysisService
from app.models.league_scoring import LeagueScoring
from app.services.grading import (
    grade_from_score,
    value_score_from_picks,
    detect_bye_week_collisions,
    bye_week_score,
    combined_grade,
    value_and_bye_strengths_weaknesses,
    bench_depth_notes,
    NFL_SEASON_GAMES,
)
from app.services.draft_assistant_service import draft_assistant

logger = logging.getLogger(__name__)

# Same fallback used elsewhere in this codebase (roster_grading.py,
# mock_draft_service.py) when a league doesn't carry real per-league starter
# settings -- a standard single-QB, 2-RB/2-WR/1-TE/1-K/1-DEF lineup.
_FALLBACK_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}


class PostDraftAnalysisService:
    """Comprehensive post-draft roster analysis and optimization"""
    
    def __init__(self, db: Session):
        self.db = db
        self.waiver_service = WaiverWireService(db)
        self.sleeper_service = SleeperService()
        self.scoring_service = ScoringCalculationService(db)
        self.matchup_service = MatchupAnalysisService(db)
    
    async def analyze_roster_comprehensive(
        self, 
        user_roster: List[Dict[str, Any]], 
        league_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Comprehensive post-draft roster analysis with improvement recommendations
        """
        try:
            # Extract roster players
            roster_players = []
            for roster_player in user_roster:
                player = self.db.query(Player).filter(
                    or_(
                        Player.id == roster_player.get('player_id'),
                        Player.name == roster_player.get('player_name')
                    )
                ).first()
                if player:
                    roster_players.append({
                        'player': player,
                        'draft_round': roster_player.get('round'),
                        'draft_pick': roster_player.get('pick')
                    })
            
            if not roster_players:
                return {"error": "No valid roster players found"}
            
            # Analyze roster composition
            composition_analysis = await self._analyze_roster_composition(roster_players, league_settings)
            
            # Evaluate individual players with league scoring context
            league_scoring_id = league_settings.get('league_scoring_id')
            player_evaluations = await self._evaluate_roster_players(roster_players, league_scoring_id)
            
            # Identify roster strengths and weaknesses
            strengths_weaknesses = await self._identify_strengths_weaknesses(
                roster_players, league_settings, composition_analysis, player_evaluations
            )
            
            # Generate position-specific improvement recommendations with matchup analysis
            improvement_recs = await self._generate_improvement_recommendations(
                roster_players, league_settings, strengths_weaknesses, composition_analysis
            )
            
            # Add matchup-driven waiver recommendations
            matchup_recommendations = await self.waiver_service.get_roster_specific_matchup_recommendations(
                user_roster, week=self.matchup_service.get_current_week()
            )
            
            # Calculate overall roster grade
            roster_grade = await self._calculate_roster_grade(roster_players, player_evaluations, league_settings)
            
            return {
                "roster_analysis": {
                    "composition": composition_analysis,
                    "player_evaluations": player_evaluations,
                    "strengths_weaknesses": strengths_weaknesses,
                    "overall_grade": roster_grade
                },
                "improvement_recommendations": improvement_recs,
                "matchup_recommendations": matchup_recommendations,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive roster analysis: {str(e)}")
            return {"error": f"Roster analysis failed: {str(e)}"}
    
    def _effective_requirements(
        self, position_counts: Dict[str, int], league_settings: Optional[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Real per-league starter requirements (FLEX-aware), falling back to
        a standard lineup only when `league_settings` carries no real
        `starters` dict. Delegates to
        `DraftAssistantService._effective_position_requirements`, the same
        helper `roster_grading.py::grade_roster` uses for connected-league
        Team Analysis grading, so this path and that one can't drift apart.
        """
        raw_starters = dict((league_settings or {}).get('starters') or {}) or _FALLBACK_STARTERS
        return draft_assistant._effective_position_requirements(position_counts, {"starters": raw_starters})

    def _score_composition(
        self, position_counts: Dict[str, int], requirements: Dict[str, int]
    ) -> Dict[str, Any]:
        """Mirrors `roster_grading._score_composition`'s formula, parameterized
        by real per-league starter requirements instead of a hardcoded
        standard lineup.
        """
        if not requirements:
            requirements = _FALLBACK_STARTERS

        composition_score = 0.0
        position_breakdown: Dict[str, Any] = {}

        for position, required_count in requirements.items():
            if required_count <= 0:
                continue
            actual_count = position_counts.get(position, 0)

            if actual_count >= required_count:
                position_score = min(100, 80 + (actual_count - required_count) * 10)
            else:
                position_score = (actual_count / required_count) * 80

            position_breakdown[position] = {
                'players_drafted': actual_count,
                'recommended_minimum': required_count,
                'depth_score': round(position_score, 1),
                'needs_attention': actual_count < required_count,
                'overstocked': actual_count > required_count + 1
            }
            composition_score += position_score

        composition_score = composition_score / len(position_breakdown) if position_breakdown else 0.0

        return {
            "composition_score": round(composition_score, 1),
            "position_breakdown": position_breakdown,
        }

    async def _analyze_roster_composition(
        self,
        roster_players: List[Dict],
        league_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze roster composition and balance"""

        # Count players by position
        position_counts = {}
        total_projected_points = 0
        normalized_players = []

        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'

            position_counts[position] = position_counts.get(position, 0) + 1
            if player.projected_points:
                total_projected_points += player.projected_points
            normalized_players.append({'position': position, 'bye_week': player.bye_week})

        # Real per-league starter requirements (FLEX-aware), not a hardcoded
        # standard lineup -- see _effective_requirements.
        requirements = self._effective_requirements(position_counts, league_settings)

        composition = self._score_composition(position_counts, requirements)
        composition_score = composition['composition_score']
        position_analysis = composition['position_breakdown']

        # Calculate depth analysis
        skill_positions = ['RB', 'WR', 'TE']
        depth_strength = sum(position_counts.get(pos, 0) for pos in skill_positions)

        bye_week_collisions = detect_bye_week_collisions(normalized_players, requirements)

        return {
            "position_breakdown": position_analysis,
            "total_players": len(roster_players),
            "composition_score": composition_score,
            "projected_total_points": round(total_projected_points, 1),
            "avg_points_per_player": round(total_projected_points / len(roster_players), 1),
            "skill_position_depth": depth_strength,
            "roster_balance_grade": self._grade_from_score(composition_score),
            "bye_week_collisions": bye_week_collisions,
            "position_requirements": requirements,
        }
    
    async def _evaluate_roster_players(self, roster_players: List[Dict], league_scoring_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Evaluate each player's draft value and season outlook"""
        evaluations = []
        
        for roster_player in roster_players:
            player = roster_player['player']
            draft_round = roster_player.get('draft_round', 0)
            
            # Get player's historical performance
            recent_performances = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player.id,
                    PlayerHistoricalPerformance.season >= 2023
                )
            ).order_by(PlayerHistoricalPerformance.season.desc()).limit(16).all()
            
            # Calculate player evaluation metrics with custom scoring if available
            value_analysis = await self._calculate_draft_value(
                player, draft_round, roster_player.get('draft_pick'), league_scoring_id
            )
            
            evaluation = {
                "player_info": {
                    "id": player.id,
                    "name": player.name,
                    "position": player.position.value if player.position else "Unknown",
                    "team": player.team,
                    "draft_round": draft_round
                },
                "value_analysis": value_analysis,
                "season_outlook": await self._generate_season_outlook(player, recent_performances),
                "risk_assessment": await self._assess_player_risk(player, recent_performances),
                "scoring_context": self._get_scoring_context(player, league_scoring_id) if league_scoring_id else None
            }
            
            evaluations.append(evaluation)
        
        # Sort by overall value score
        evaluations.sort(key=lambda x: x['value_analysis']['overall_value_score'], reverse=True)
        
        return evaluations
    
    @staticmethod
    def _value_category_and_grade(value_percentage: float) -> Tuple[str, str]:
        if value_percentage >= 120:
            return "Excellent Value", "A"
        elif value_percentage >= 110:
            return "Good Value", "B"
        elif value_percentage >= 90:
            return "Fair Value", "C"
        elif value_percentage >= 70:
            return "Slight Reach", "D"
        else:
            return "Significant Reach", "F"

    async def _calculate_draft_value(
        self,
        player: Player,
        draft_round: int,
        draft_pick: Optional[int] = None,
        league_scoring_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calculate if player was good value at draft position.

        Primary signal: real ADP (`Player.adp`) vs. the actual overall pick
        the player was drafted at -- mirrors
        `mock_draft_service._pick_value`'s logic (that function also checks
        `search_rank`, but `Player` has no such column, only `adp`).
        Only falls back to the old round-expectations-vs-projected-points
        estimate when there's no real ADP or no known overall pick.
        """
        try:
            # Use league-specific scoring if available
            if league_scoring_id:
                custom_points = self.scoring_service.get_player_points_with_custom_scoring(
                    player.id, league_scoring_id, 2024
                )
                projected_points = custom_points.get('total_points', player.projected_points or 0)
            else:
                projected_points = player.projected_points or 0

            adp = player.adp

            if adp is not None and adp > 0 and draft_pick is not None and draft_pick > 0:
                # Real ADP signal: picked later than ADP suggested (pick > adp)
                # is good value; picked earlier (reach) is bad value.
                value_percentage = (draft_pick / adp) * 100
                expected_points_for_round = None
                value_over_expectation = None
                value_source = "adp"
            else:
                # Fallback: rough expected-points-by-round estimate.
                round_expectations = {
                    1: 250, 2: 220, 3: 190, 4: 160, 5: 140, 6: 120,
                    7: 100, 8: 85, 9: 75, 10: 65, 11: 55, 12: 50
                }
                expected_points_for_round = round_expectations.get(draft_round, 40)
                value_over_expectation = round(projected_points - expected_points_for_round, 1)
                value_percentage = (
                    (projected_points / expected_points_for_round * 100)
                    if expected_points_for_round > 0 else 100
                )
                value_source = "projected_points_vs_round"

            value_category, value_grade = self._value_category_and_grade(value_percentage)

            return {
                "overall_value_score": round(value_percentage, 1),
                "value_percentage": round(value_percentage, 1),
                "value_category": value_category,
                "value_grade": value_grade,
                "projected_points": projected_points,
                "expected_points_for_round": expected_points_for_round,
                "value_over_expectation": value_over_expectation,
                "value_source": value_source,
                "adp": adp,
                "draft_pick": draft_pick,
            }

        except Exception as e:
            logger.error(f"Error calculating draft value for {player.name}: {str(e)}")
            return {
                "overall_value_score": 50,
                "value_percentage": None,
                "value_category": "Unable to Calculate",
                "value_grade": "N/A",
                "error": str(e)
            }
    
    async def _generate_season_outlook(self, player: Player, performances: List) -> Dict[str, Any]:
        """Generate season outlook for player"""
        if not performances:
            return {
                "outlook": "Limited Data",
                "confidence": "Low",
                "key_factors": ["Insufficient historical data for analysis"]
            }
        
        # Calculate recent trends
        recent_points = [p.fantasy_points_ppr for p in performances[-8:] if p.fantasy_points_ppr]
        early_points = [p.fantasy_points_ppr for p in performances[:8] if p.fantasy_points_ppr]
        
        outlook_factors = []
        confidence_score = 50
        
        if len(recent_points) >= 3 and len(early_points) >= 3:
            recent_avg = np.mean(recent_points)
            early_avg = np.mean(early_points)
            trend = (recent_avg - early_avg) / early_avg if early_avg > 0 else 0
            
            if trend > 0.15:
                outlook_factors.append("Strong positive trend in recent performances")
                confidence_score += 20
                outlook = "Very Positive"
            elif trend > 0.05:
                outlook_factors.append("Modest improvement in recent games")
                confidence_score += 10
                outlook = "Positive"
            elif trend < -0.15:
                outlook_factors.append("Concerning decline in recent performances")
                confidence_score -= 20
                outlook = "Concerning"
            elif trend < -0.05:
                outlook_factors.append("Slight decline in recent form")
                confidence_score -= 10
                outlook = "Neutral"
            else:
                outlook_factors.append("Consistent performance level")
                outlook = "Stable"
        else:
            outlook = "Limited Data"
        
        # Add injury context
        if player.injury_status and player.injury_status != 'HEALTHY':
            outlook_factors.append(f"Currently listed as {player.injury_status}")
            confidence_score -= 15
        
        # Add age/experience factors
        total_games = len(performances)
        if total_games < 16:
            outlook_factors.append("Limited NFL experience - higher variance expected")
        elif total_games > 64:
            outlook_factors.append("Veteran player with established track record")
            confidence_score += 10
        
        confidence_level = "High" if confidence_score >= 70 else "Medium" if confidence_score >= 40 else "Low"
        
        return {
            "outlook": outlook,
            "confidence": confidence_level,
            "confidence_score": max(0, min(100, confidence_score)),
            "key_factors": outlook_factors,
            "games_analyzed": total_games
        }
    
    async def _assess_player_risk(self, player: Player, performances: List) -> Dict[str, Any]:
        """Assess injury and performance risk for player"""
        risk_factors = []
        risk_score = 0  # Lower is better
        
        # Injury history analysis
        if player.injury_status and player.injury_status != 'HEALTHY':
            risk_score += 30
            risk_factors.append(f"Currently {player.injury_status}")
        
        # Performance consistency
        if performances:
            points = [p.fantasy_points_ppr for p in performances if p.fantasy_points_ppr]
            if len(points) > 1:
                cv = np.std(points) / np.mean(points) if np.mean(points) > 0 else 1
                if cv > 0.6:
                    risk_score += 20
                    risk_factors.append("High performance volatility")
                elif cv < 0.3:
                    risk_score -= 10
                    risk_factors.append("Consistent weekly production")
        
        # Age and workload factors
        position = player.position.value if player.position else ""
        if position == "RB" and len(performances) > 48:  # 3+ years
            risk_score += 15
            risk_factors.append("RB with significant career workload")
        
        # Determine risk level
        if risk_score <= 10:
            risk_level = "Low"
            risk_color = "green"
        elif risk_score <= 30:
            risk_level = "Medium"
            risk_color = "yellow"
        else:
            risk_level = "High" 
            risk_color = "red"
        
        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_color": risk_color,
            "risk_factors": risk_factors,
            "injury_status": player.injury_status or "HEALTHY"
        }
    
    async def _identify_strengths_weaknesses(
        self,
        roster_players: List[Dict],
        league_settings: Dict[str, Any],
        composition_analysis: Optional[Dict[str, Any]] = None,
        player_evaluations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Identify roster strengths and weaknesses.

        Two independent signal sets, merged: the count/avg-projected-points
        heuristics below (unchanged), plus real per-league-requirement,
        ADP-value, and bye-week signals via `grading
        .value_and_bye_strengths_weaknesses` -- previously this method never
        looked at `league_settings`, `player_evaluations`, or bye weeks at
        all, so e.g. a specific overpaid pick or a bye-week collision never
        showed up here even after `_calculate_roster_grade` started scoring
        on exactly those signals.
        """

        # Group players by position
        position_groups = {}
        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'
            
            if position not in position_groups:
                position_groups[position] = []
            position_groups[position].append(player)
        
        strengths = []
        weaknesses = []

        # Real per-league starter counts when available -- see
        # roster_grading.py::_identify_strengths_weaknesses's docstring for
        # why quality is computed from only the top `requirements[position]`
        # players (this league's real starter count), not the whole
        # rostered group: averaging in committee/backup-grade depth either
        # hides a genuinely strong top end or falsely inflates a mediocre
        # one, which is exactly the "Excellent RB depth" bug a user reported
        # against a real 5-RB roster (2 real starters + 3 committee backs).
        effective_requirements = (composition_analysis or {}).get("position_requirements") or {}

        # Analyze each position group
        for position, players in position_groups.items():
            starter_count = max(effective_requirements.get(position, 1), 1)
            sorted_players = sorted(players, key=lambda p: p.projected_points or 0, reverse=True)
            starters = sorted_players[:starter_count]
            # `projected_points` (ESPN-sourced today) is a real season-long
            # total, not a per-game rate -- see NFL_SEASON_GAMES's docstring
            # in grading.py. Divide before comparing against the
            # weekly-shaped thresholds below.
            avg_projection = np.mean([(p.projected_points or 0) / NFL_SEASON_GAMES for p in starters]) if starters else 0.0
            player_count = len(players)
            
            # Position-specific analysis
            if position == 'QB':
                if player_count >= 2 and avg_projection >= 18:
                    strengths.append(f"Strong QB depth with {player_count} quality options")
                elif player_count == 1 and avg_projection < 15:
                    weaknesses.append("Weak QB situation - consider backup or upgrade")
                elif player_count == 0:
                    weaknesses.append("No QB drafted - critical need")
            
            elif position == 'RB':
                if player_count >= 3 and avg_projection >= 12:
                    strengths.append(f"Excellent RB depth with {player_count} backs")
                elif player_count < 2:
                    weaknesses.append("Insufficient RB depth - high injury risk")
                elif avg_projection < 8:
                    weaknesses.append("RB room lacks upside - consider upgrades")
            
            elif position == 'WR':
                if player_count >= 4 and avg_projection >= 10:
                    strengths.append(f"Deep WR corps with {player_count} receivers")
                elif player_count < 3:
                    weaknesses.append("Thin at WR - need more depth")
                elif avg_projection < 6:
                    weaknesses.append("WR group lacks consistent producers")
            
            elif position == 'TE':
                if player_count >= 1 and avg_projection >= 8:
                    strengths.append("Solid TE situation")
                elif avg_projection < 5:
                    weaknesses.append("TE position is a concern - consider streaming")
                elif player_count == 0:
                    weaknesses.append("No TE drafted")
        
        # Overall depth analysis
        skill_players = position_groups.get('RB', []) + position_groups.get('WR', []) + position_groups.get('TE', [])
        if len(skill_players) >= 7:
            strengths.append("Strong overall skill position depth")
        elif len(skill_players) < 5:
            weaknesses.append("Lacks sufficient skill position depth")

        value_entries = None
        if player_evaluations:
            value_entries = [
                {
                    "player_name": ev["player_info"]["name"],
                    "position": ev["player_info"]["position"],
                    "pick": ev["value_analysis"].get("draft_pick"),
                    "round": ev["player_info"].get("draft_round"),
                    "value_percentage": ev["value_analysis"].get("value_percentage"),
                }
                for ev in player_evaluations
            ]

        real_position_breakdown = (composition_analysis or {}).get("position_breakdown", {})
        bye_week_collisions = (composition_analysis or {}).get("bye_week_collisions", [])
        requirements = (composition_analysis or {}).get("position_requirements", {})

        # The per-position rules above only look at headcount/avg-projection
        # and have no idea what this league actually requires, so they can
        # call a position "solid"/"deep" while the real required-depth check
        # below flags it as needing attention (or vice versa) -- e.g. "Solid
        # TE situation" alongside "TE is below your league's required depth
        # (1/3)". Let the real, league-aware signal win: drop the legacy
        # per-position entry whenever it contradicts it.
        needs_attention_positions = {
            pos for pos, info in real_position_breakdown.items() if info.get("needs_attention")
        }
        overstocked_positions = {
            pos for pos, info in real_position_breakdown.items() if info.get("overstocked")
        }
        strengths = [
            s for s in strengths
            if not any(re.search(rf"\b{re.escape(pos)}\b", s) for pos in needs_attention_positions)
        ]
        weaknesses = [
            w for w in weaknesses
            if not any(re.search(rf"\b{re.escape(pos)}\b", w) for pos in overstocked_positions)
        ]

        value_sw = value_and_bye_strengths_weaknesses(
            real_position_breakdown,
            bye_collisions=bye_week_collisions,
            value_entries=value_entries,
        )
        strengths = strengths + [s for s in value_sw["strengths"] if s not in strengths]
        weaknesses = weaknesses + [w for w in value_sw["weaknesses"] if w not in weaknesses]

        # Catches a "stud, stud, then a cliff" position that the plain
        # per-position average above can average away entirely (see
        # grading.bench_depth_notes docstring).
        if requirements:
            normalized_players = [
                {"position": pos, "projected_points": p.projected_points or 0}
                for pos, players in position_groups.items()
                for p in players
            ]
            weaknesses += bench_depth_notes(normalized_players, requirements)

        return {
            "position_breakdown": {pos: len(players) for pos, players in position_groups.items()},
            "strengths": strengths,
            "weaknesses": weaknesses,
            "bye_week_collisions": bye_week_collisions,
            "total_skill_players": len(skill_players)
        }
    
    # Positions whose real quantity shortfall is treated as high-urgency
    # (mirrors the old string-matched QB/RB "High" vs. WR/TE "Medium"
    # priority split, now keyed off the real position code instead of
    # substring-matching prose).
    _HIGH_PRIORITY_NEED_POSITIONS = {"QB", "RB"}

    async def _generate_improvement_recommendations(
        self,
        roster_players: List[Dict],
        league_settings: Dict[str, Any],
        strengths_weaknesses: Dict[str, Any],
        composition_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate specific waiver wire targets for roster improvement.

        Immediate needs are decided ONLY from
        `composition_analysis["position_breakdown"][pos]["needs_attention"]`
        -- a real boolean already computed against real per-league starter
        requirements by `_analyze_roster_composition` -- never by
        substring-matching the free-text weakness sentences from
        `_identify_strengths_weaknesses`. Those sentences now also include
        bench-depth-cliff notes (`grading.bench_depth_notes`, e.g. "RB depth
        beyond your top 2 is thin...") and bye-week-collision notes
        (`grading.value_and_bye_strengths_weaknesses`, e.g. "Week 11: every
        rostered QB is on bye...") which mention a position code but are
        NOT a "you need to add another player at this position" quantity
        signal -- naive `'RB' in weakness` matching would misfire on both.
        Those two sentence types are routed to their own
        `depth_concerns` / `bye_week_concerns` buckets instead, and never
        feed `immediate_needs`.
        """

        recommendations = {
            "immediate_needs": [],
            "depth_improvements": [],
            "upside_targets": [],
            "handcuff_recommendations": [],
            "depth_concerns": [],
            "bye_week_concerns": [],
        }

        # Current roster positions + a lowercase name set for filtering
        # waiver candidates already on this roster.
        current_positions = {}
        rostered_names = set()

        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'
            current_positions[position] = current_positions.get(position, 0) + 1
            rostered_names.add(player.name.lower())

        # --- Real quantity needs: needs_attention only, never prose. ---
        position_breakdown = (composition_analysis or {}).get("position_breakdown", {})
        for position, info in position_breakdown.items():
            if not info.get("needs_attention"):
                continue

            priority = "High" if position in self._HIGH_PRIORITY_NEED_POSITIONS else "Medium"
            drafted = info.get("players_drafted")
            required = info.get("recommended_minimum")
            reasoning = (
                f"{position} is below your league's required depth "
                f"({drafted}/{required} rostered)."
            )

            targets = []
            try:
                candidates = await self.waiver_service.get_live_trending_recommendations(
                    position=position, limit=3
                )
            except Exception as e:
                logger.error(f"Error fetching waiver targets for {position}: {str(e)}")
                candidates = []

            for candidate in candidates:
                candidate_name = (candidate.get("player_name") or "")
                if candidate_name.lower() in rostered_names:
                    continue
                targets.append({
                    "player_name": candidate.get("player_name"),
                    "position": candidate.get("position"),
                    "team": candidate.get("team"),
                    "confidence_score": candidate.get("confidence_score"),
                    "reason": candidate.get("reason"),
                })
                if len(targets) >= 3:
                    break

            recommendations["immediate_needs"].append({
                "position": position,
                "priority": priority,
                "reasoning": reasoning,
                "targets": targets,
            })

        # --- Bench-quality / bye-week signals: informational only, kept
        # separate so they can never masquerade as a quantity need above. ---
        for weakness in strengths_weaknesses.get('weaknesses', []):
            if weakness.startswith("Week ") and "on bye" in weakness:
                recommendations["bye_week_concerns"].append(weakness)
            elif "depth beyond your top" in weakness:
                recommendations["depth_concerns"].append(weakness)

        # Add general improvement suggestions
        if current_positions.get('RB', 0) >= 2:
            recommendations["handcuff_recommendations"].append({
                "reasoning": "Protect your RB investments with handcuffs",
                "target_criteria": "Backup RBs for your starters"
            })

        if current_positions.get('WR', 0) >= 3:
            recommendations["upside_targets"].append({
                "position": "WR",
                "reasoning": "Target high-upside WRs for potential breakouts",
                "target_criteria": "Young WRs with increasing target share"
            })

        return recommendations
    
    async def get_personalized_waiver_targets(
        self, 
        user_roster: List[Dict[str, Any]], 
        week: int = 1
    ) -> Dict[str, Any]:
        """Get waiver wire targets specifically for this roster's needs"""
        
        try:
            # Analyze current roster
            roster_analysis = await self.analyze_roster_comprehensive(user_roster, {})
            
            # Get general waiver recommendations
            general_waivers = await self.waiver_service.generate_weekly_recommendations(week)
            
            # Filter and prioritize based on roster needs
            personalized_targets = []
            
            # Extract roster weaknesses
            weaknesses = roster_analysis.get('roster_analysis', {}).get('strengths_weaknesses', {}).get('weaknesses', [])
            weak_positions = []
            
            for weakness in weaknesses:
                if 'QB' in weakness:
                    weak_positions.append('QB')
                elif 'RB' in weakness:
                    weak_positions.append('RB')
                elif 'WR' in weakness:
                    weak_positions.append('WR')
                elif 'TE' in weakness:
                    weak_positions.append('TE')
            
            # Prioritize waiver targets based on roster needs
            for waiver_rec in general_waivers:
                player_position = waiver_rec.get('position', '')
                base_priority = waiver_rec.get('confidence_score', 0)
                
                # Boost priority for positions of need
                if player_position in weak_positions:
                    adjusted_priority = min(100, base_priority + 25)
                    personalized_targets.append({
                        **waiver_rec,
                        'adjusted_priority': adjusted_priority,
                        'roster_fit': 'Addresses Position Need',
                        'personalized_reasoning': f"Fills weakness at {player_position}"
                    })
                elif base_priority >= 70:  # High-value general targets
                    personalized_targets.append({
                        **waiver_rec,
                        'adjusted_priority': base_priority,
                        'roster_fit': 'High-Value Depth',
                        'personalized_reasoning': 'Strong waiver option regardless of need'
                    })
            
            # Sort by adjusted priority
            personalized_targets.sort(key=lambda x: x['adjusted_priority'], reverse=True)
            
            return {
                "roster_summary": {
                    "total_players": len(user_roster),
                    "identified_weaknesses": weaknesses,
                    "weak_positions": weak_positions
                },
                "personalized_targets": personalized_targets[:15],  # Top 15 targets
                "analysis_reasoning": "Recommendations prioritized based on your roster composition and identified needs",
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating personalized waiver targets: {str(e)}")
            return {"error": f"Failed to generate personalized targets: {str(e)}"}
    
    async def _calculate_roster_grade(
        self,
        roster_players: List[Dict],
        evaluations: List[Dict],
        league_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Calculate overall roster grade.

        Combines composition (real per-league starter requirements, see
        _effective_requirements), draft value (real ADP-vs-pick where
        available, see _calculate_draft_value), and bye-week collision
        signals via the shared `grading.combined_grade` primitive, instead of
        an ad-hoc avg_value_score - balance_penalty formula.
        """

        if not evaluations:
            return {"grade": "N/A", "score": 0, "reasoning": "No player evaluations available"}

        # Real per-position counts + real per-league starter requirements.
        position_counts = {}
        normalized_players = []
        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'
            position_counts[position] = position_counts.get(position, 0) + 1
            normalized_players.append({'position': position, 'bye_week': player.bye_week})

        requirements = self._effective_requirements(position_counts, league_settings)

        composition = self._score_composition(position_counts, requirements)
        composition_score = composition['composition_score']

        # Draft-value component: reuse each evaluation's already-computed
        # value_percentage (real ADP-vs-pick where available).
        value_entries = [
            {'value_percentage': eval_data['value_analysis'].get('value_percentage')}
            for eval_data in evaluations
        ]
        value_score = value_score_from_picks(value_entries)

        scored_values = [v['value_percentage'] for v in value_entries if v['value_percentage'] is not None]
        avg_value_score = round(sum(scored_values) / len(scored_values), 1) if scored_values else 0.0

        # Bye-week collision component.
        collisions = detect_bye_week_collisions(normalized_players, requirements)
        byes_score = bye_week_score(collisions)

        combined = combined_grade(
            composition_score=composition_score,
            value_score=value_score,
            bye_weeks_score=byes_score,
        )

        # Kept for backward compatibility with existing callers/UI that read
        # a flat "balance_penalty" -- same rule as before (10pt penalty per
        # under-filled required position), just against real requirements.
        balance_penalty = 0
        for pos, min_count in requirements.items():
            if position_counts.get(pos, 0) < min_count:
                balance_penalty += 10

        description_by_grade = {
            "A": "Excellent Draft",
            "B": "Good Draft",
            "C": "Average Draft",
            "D": "Below Average",
            "F": "Poor Draft",
        }

        return {
            "grade": combined["grade"],
            "score": combined["overall_score"],
            "description": description_by_grade.get(combined["grade"], "Average Draft"),
            "player_count": len(roster_players),
            "avg_player_value": avg_value_score,
            "balance_penalty": balance_penalty,
            "components": combined["components"],
            "bye_week_collisions": collisions,
        }
    
    def _grade_from_score(self, score: float) -> str:
        """Convert numeric score to letter grade.

        Delegates to the shared `grading.grade_from_score` so this and the
        mock-draft grading path (`mock_draft_service.py`) can't drift apart.
        """
        return grade_from_score(score)
    
    def _get_scoring_context(self, player: Player, league_scoring_id: int) -> Dict[str, Any]:
        """Get scoring context for a player in a specific league"""
        try:
            scoring_config = self.db.query(LeagueScoring).filter(
                LeagueScoring.id == league_scoring_id
            ).first()
            
            if not scoring_config:
                return {"error": "Scoring configuration not found"}
            
            # Analyze how this scoring system affects this player
            context = {
                "scoring_type": scoring_config.scoring_type.value,
                "advantages": [],
                "disadvantages": []
            }
            
            position = player.position.value if player.position else ""
            
            # Position-specific scoring advantages
            if position in ["WR", "TE", "RB"] and scoring_config.reception_points > 0:
                context["advantages"].append(f"Benefits from {scoring_config.reception_points} points per reception")
            
            if position == "QB":
                if scoring_config.passing_300_yard_bonus > 0:
                    context["advantages"].append(f"{scoring_config.passing_300_yard_bonus} point bonus for 300+ passing yards")
                if scoring_config.passing_int_points < -1:
                    context["disadvantages"].append("Heavy penalty for interceptions")
            
            if position == "RB":
                if scoring_config.rushing_100_yard_bonus > 0:
                    context["advantages"].append(f"{scoring_config.rushing_100_yard_bonus} point bonus for 100+ rushing yards")
            
            if position in ["WR", "TE"]:
                if scoring_config.receiving_100_yard_bonus > 0:
                    context["advantages"].append(f"{scoring_config.receiving_100_yard_bonus} point bonus for 100+ receiving yards")
            
            # Advanced scoring benefits
            if scoring_config.target_points > 0 and position in ["WR", "TE", "RB"]:
                context["advantages"].append(f"{scoring_config.target_points} points per target")
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting scoring context: {str(e)}")
            return {"error": str(e)}