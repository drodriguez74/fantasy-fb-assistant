"""
Post-Draft Analysis Service

Provides comprehensive roster evaluation and personalized waiver wire recommendations
after completing a fantasy football draft.
"""

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

logger = logging.getLogger(__name__)


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
                    Player.id == roster_player.get('player_id') or
                    Player.name == roster_player.get('player_name')
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
            strengths_weaknesses = await self._identify_strengths_weaknesses(roster_players, league_settings)
            
            # Generate position-specific improvement recommendations with matchup analysis
            improvement_recs = await self._generate_improvement_recommendations(
                roster_players, league_settings, strengths_weaknesses
            )
            
            # Add matchup-driven waiver recommendations
            matchup_recommendations = await self.waiver_service.get_roster_specific_matchup_recommendations(
                user_roster, week=self.matchup_service.get_current_week()
            )
            
            # Calculate overall roster grade
            roster_grade = await self._calculate_roster_grade(roster_players, player_evaluations)
            
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
    
    async def _analyze_roster_composition(
        self, 
        roster_players: List[Dict], 
        league_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze roster composition and balance"""
        
        # Count players by position
        position_counts = {}
        total_projected_points = 0
        
        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'
            
            position_counts[position] = position_counts.get(position, 0) + 1
            if player.projected_points:
                total_projected_points += player.projected_points
        
        # Standard roster requirements
        standard_lineup = {
            'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1, 'K': 1, 'DEF': 1
        }
        
        # Analyze balance
        composition_score = 0
        position_analysis = {}
        
        for position, standard_count in standard_lineup.items():
            actual_count = position_counts.get(position, 0)
            
            # Score based on how well position is filled
            if actual_count >= standard_count:
                position_score = min(100, 80 + (actual_count - standard_count) * 10)
            else:
                position_score = (actual_count / standard_count) * 80
            
            position_analysis[position] = {
                'players_drafted': actual_count,
                'recommended_minimum': standard_count,
                'depth_score': position_score,
                'needs_attention': actual_count < standard_count,
                'overstocked': actual_count > standard_count + 1
            }
            
            composition_score += position_score
        
        composition_score = composition_score / len(standard_lineup)
        
        # Calculate depth analysis
        skill_positions = ['RB', 'WR', 'TE']
        depth_strength = sum(position_counts.get(pos, 0) for pos in skill_positions)
        
        return {
            "position_breakdown": position_analysis,
            "total_players": len(roster_players),
            "composition_score": round(composition_score, 1),
            "projected_total_points": round(total_projected_points, 1),
            "avg_points_per_player": round(total_projected_points / len(roster_players), 1),
            "skill_position_depth": depth_strength,
            "roster_balance_grade": self._grade_from_score(composition_score)
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
            value_analysis = await self._calculate_draft_value(player, draft_round, league_scoring_id)
            
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
    
    async def _calculate_draft_value(self, player: Player, draft_round: int, league_scoring_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculate if player was good value at draft position"""
        try:
            # Expected points based on draft round (rough estimates)
            round_expectations = {
                1: 250, 2: 220, 3: 190, 4: 160, 5: 140, 6: 120,
                7: 100, 8: 85, 9: 75, 10: 65, 11: 55, 12: 50
            }
            
            expected_points = round_expectations.get(draft_round, 40)
            
            # Use league-specific scoring if available
            if league_scoring_id:
                custom_points = self.scoring_service.get_player_points_with_custom_scoring(
                    player.id, league_scoring_id, 2024
                )
                projected_points = custom_points.get('total_points', player.projected_points or 0)
            else:
                projected_points = player.projected_points or 0
            
            # Calculate value metrics
            value_over_expectation = projected_points - expected_points
            value_percentage = (projected_points / expected_points * 100) if expected_points > 0 else 100
            
            # Determine value category
            if value_percentage >= 120:
                value_category = "Excellent Value"
                value_grade = "A"
            elif value_percentage >= 110:
                value_category = "Good Value"
                value_grade = "B"
            elif value_percentage >= 90:
                value_category = "Fair Value"
                value_grade = "C"
            elif value_percentage >= 70:
                value_category = "Slight Reach"
                value_grade = "D"
            else:
                value_category = "Significant Reach"
                value_grade = "F"
            
            return {
                "overall_value_score": round(value_percentage, 1),
                "value_category": value_category,
                "value_grade": value_grade,
                "projected_points": projected_points,
                "expected_points_for_round": expected_points,
                "value_over_expectation": round(value_over_expectation, 1)
            }
            
        except Exception as e:
            logger.error(f"Error calculating draft value for {player.name}: {str(e)}")
            return {
                "overall_value_score": 50,
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
        league_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Identify roster strengths and weaknesses"""
        
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
        
        # Analyze each position group
        for position, players in position_groups.items():
            avg_projection = np.mean([p.projected_points or 0 for p in players])
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
        
        return {
            "position_breakdown": {pos: len(players) for pos, players in position_groups.items()},
            "strengths": strengths,
            "weaknesses": weaknesses,
            "total_skill_players": len(skill_players)
        }
    
    async def _generate_improvement_recommendations(
        self, 
        roster_players: List[Dict], 
        league_settings: Dict[str, Any],
        strengths_weaknesses: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate specific waiver wire targets for roster improvement"""
        
        recommendations = {
            "immediate_needs": [],
            "depth_improvements": [],
            "upside_targets": [],
            "handcuff_recommendations": []
        }
        
        # Current roster positions
        current_positions = {}
        rb_names = []
        
        for roster_player in roster_players:
            player = roster_player['player']
            position = player.position.value if player.position else 'UNKNOWN'
            current_positions[position] = current_positions.get(position, 0) + 1
            
            if position == 'RB':
                rb_names.append(player.name.lower())
        
        # Generate position-specific recommendations
        weaknesses = strengths_weaknesses.get('weaknesses', [])
        
        for weakness in weaknesses:
            if 'QB' in weakness:
                recommendations["immediate_needs"].append({
                    "position": "QB",
                    "priority": "High",
                    "reasoning": weakness,
                    "target_criteria": "QB with 15+ projected points, favorable schedule"
                })
            elif 'RB' in weakness:
                recommendations["immediate_needs"].append({
                    "position": "RB",
                    "priority": "High", 
                    "reasoning": weakness,
                    "target_criteria": "RB with clear role, 8+ projected points"
                })
            elif 'WR' in weakness:
                recommendations["immediate_needs"].append({
                    "position": "WR",
                    "priority": "Medium",
                    "reasoning": weakness,
                    "target_criteria": "WR with target share upside, favorable upcoming matchups"
                })
            elif 'TE' in weakness:
                recommendations["immediate_needs"].append({
                    "position": "TE",
                    "priority": "Medium",
                    "reasoning": weakness,
                    "target_criteria": "TE with red zone usage or streaming options"
                })
        
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
    
    async def _calculate_roster_grade(self, roster_players: List[Dict], evaluations: List[Dict]) -> Dict[str, Any]:
        """Calculate overall roster grade"""
        
        if not evaluations:
            return {"grade": "N/A", "score": 0, "reasoning": "No player evaluations available"}
        
        # Calculate weighted average of player values
        total_value_score = sum(eval_data['value_analysis']['overall_value_score'] for eval_data in evaluations)
        avg_value_score = total_value_score / len(evaluations)
        
        # Adjust based on roster balance
        position_counts = {}
        for roster_player in roster_players:
            position = roster_player['player'].position.value if roster_player['player'].position else 'UNKNOWN'
            position_counts[position] = position_counts.get(position, 0) + 1
        
        # Penalty for missing key positions
        balance_penalty = 0
        required_positions = {'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1}
        
        for pos, min_count in required_positions.items():
            if position_counts.get(pos, 0) < min_count:
                balance_penalty += 10
        
        final_score = max(0, avg_value_score - balance_penalty)
        
        # Assign letter grade
        if final_score >= 90:
            grade = "A"
            description = "Excellent Draft"
        elif final_score >= 80:
            grade = "B"
            description = "Good Draft"
        elif final_score >= 70:
            grade = "C"
            description = "Average Draft"
        elif final_score >= 60:
            grade = "D"
            description = "Below Average"
        else:
            grade = "F"
            description = "Poor Draft"
        
        return {
            "grade": grade,
            "score": round(final_score, 1),
            "description": description,
            "player_count": len(roster_players),
            "avg_player_value": round(avg_value_score, 1),
            "balance_penalty": balance_penalty
        }
    
    def _grade_from_score(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 90: return "A"
        elif score >= 80: return "B"
        elif score >= 70: return "C"
        elif score >= 60: return "D"
        else: return "F"
    
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