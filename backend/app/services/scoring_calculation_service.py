"""
Scoring Calculation Service

Calculates fantasy points based on league-specific scoring settings including
custom bonuses, yardage requirements, and penalty systems.
"""

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.league_scoring import LeagueScoring, ScoringPreset, PlayerScoringCalculation
from app.models.historical_performance import PlayerHistoricalPerformance
from app.models.player import Player

logger = logging.getLogger(__name__)


class ScoringCalculationService:
    """Service for calculating fantasy points with custom league scoring"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_fantasy_points(
        self, 
        stats: Dict[str, Any], 
        scoring_config: LeagueScoring,
        position: str
    ) -> Dict[str, Any]:
        """
        Calculate fantasy points based on raw stats and league scoring configuration
        """
        try:
            points_breakdown = {}
            total_points = 0.0
            
            # Passing statistics (QB)
            if position == "QB" and stats.get('passing_stats'):
                passing_stats = stats['passing_stats']
                
                # Passing yards
                if passing_stats.get('yards'):
                    yards_points = passing_stats['yards'] / scoring_config.passing_yards_per_point
                    points_breakdown['passing_yards'] = round(yards_points, 2)
                    total_points += yards_points
                
                # Passing TDs
                if passing_stats.get('touchdowns'):
                    td_points = passing_stats['touchdowns'] * scoring_config.passing_td_points
                    points_breakdown['passing_tds'] = td_points
                    total_points += td_points
                
                # Interceptions
                if passing_stats.get('interceptions'):
                    int_points = passing_stats['interceptions'] * scoring_config.passing_int_points
                    points_breakdown['interceptions'] = int_points
                    total_points += int_points
                
                # Passing bonuses
                if passing_stats.get('yards', 0) >= 300 and scoring_config.passing_300_yard_bonus:
                    bonus_points = scoring_config.passing_300_yard_bonus
                    points_breakdown['300_yard_bonus'] = bonus_points
                    total_points += bonus_points
                
                if passing_stats.get('yards', 0) >= 400 and scoring_config.passing_400_yard_bonus:
                    bonus_points = scoring_config.passing_400_yard_bonus
                    points_breakdown['400_yard_bonus'] = bonus_points
                    total_points += bonus_points
            
            # Rushing statistics (RB, QB, WR)
            if stats.get('rushing_stats'):
                rushing_stats = stats['rushing_stats']
                
                # Rushing yards
                if rushing_stats.get('yards'):
                    yards_points = rushing_stats['yards'] / scoring_config.rushing_yards_per_point
                    points_breakdown['rushing_yards'] = round(yards_points, 2)
                    total_points += yards_points
                
                # Rushing TDs
                if rushing_stats.get('touchdowns'):
                    td_points = rushing_stats['touchdowns'] * scoring_config.rushing_td_points
                    points_breakdown['rushing_tds'] = td_points
                    total_points += td_points
                
                # Rushing bonuses
                if rushing_stats.get('yards', 0) >= 100 and scoring_config.rushing_100_yard_bonus:
                    bonus_points = scoring_config.rushing_100_yard_bonus
                    points_breakdown['100_yard_rushing_bonus'] = bonus_points
                    total_points += bonus_points
            
            # Receiving statistics (WR, TE, RB)
            if stats.get('receiving_stats'):
                receiving_stats = stats['receiving_stats']
                
                # Receiving yards
                if receiving_stats.get('yards'):
                    yards_points = receiving_stats['yards'] / scoring_config.receiving_yards_per_point
                    points_breakdown['receiving_yards'] = round(yards_points, 2)
                    total_points += yards_points
                
                # Receiving TDs
                if receiving_stats.get('touchdowns'):
                    td_points = receiving_stats['touchdowns'] * scoring_config.receiving_td_points
                    points_breakdown['receiving_tds'] = td_points
                    total_points += td_points
                
                # Receptions (PPR)
                if receiving_stats.get('receptions'):
                    rec_points = receiving_stats['receptions'] * scoring_config.reception_points
                    points_breakdown['receptions'] = rec_points
                    total_points += rec_points
                
                # Receiving bonuses
                if receiving_stats.get('yards', 0) >= 100 and scoring_config.receiving_100_yard_bonus:
                    bonus_points = scoring_config.receiving_100_yard_bonus
                    points_breakdown['100_yard_receiving_bonus'] = bonus_points
                    total_points += bonus_points
            
            # Kicking statistics (K)
            if position == "K" and stats.get('kicking_stats'):
                kicking_stats = stats['kicking_stats']
                
                # Field goals by distance
                if kicking_stats.get('fg_made_0_39'):
                    fg_points = kicking_stats['fg_made_0_39'] * scoring_config.fg_0_39_points
                    points_breakdown['fg_0_39'] = fg_points
                    total_points += fg_points
                
                if kicking_stats.get('fg_made_40_49'):
                    fg_points = kicking_stats['fg_made_40_49'] * scoring_config.fg_40_49_points
                    points_breakdown['fg_40_49'] = fg_points
                    total_points += fg_points
                
                if kicking_stats.get('fg_made_50_plus'):
                    fg_points = kicking_stats['fg_made_50_plus'] * scoring_config.fg_50_plus_points
                    points_breakdown['fg_50_plus'] = fg_points
                    total_points += fg_points
                
                # Extra points
                if kicking_stats.get('extra_points_made'):
                    xp_points = kicking_stats['extra_points_made'] * scoring_config.extra_point_points
                    points_breakdown['extra_points'] = xp_points
                    total_points += xp_points
            
            # Defense/Special Teams (DEF)
            if position == "DEF" and stats.get('defensive_stats'):
                def_stats = stats['defensive_stats']
                
                # Defensive stats
                for stat, points_per in [
                    ('sacks', scoring_config.def_sack_points),
                    ('interceptions', scoring_config.def_int_points),
                    ('fumble_recoveries', scoring_config.def_fumble_rec_points),
                    ('touchdowns', scoring_config.def_td_points),
                    ('safeties', scoring_config.def_safety_points),
                    ('blocked_kicks', scoring_config.def_block_kick_points)
                ]:
                    if def_stats.get(stat):
                        stat_points = def_stats[stat] * points_per
                        points_breakdown[f'def_{stat}'] = stat_points
                        total_points += stat_points
                
                # Points allowed scoring
                points_allowed = def_stats.get('points_allowed', 999)
                if points_allowed == 0:
                    pa_points = scoring_config.def_0_points_allowed
                elif points_allowed <= 6:
                    pa_points = scoring_config.def_1_6_points_allowed
                elif points_allowed <= 13:
                    pa_points = scoring_config.def_7_13_points_allowed
                elif points_allowed <= 20:
                    pa_points = scoring_config.def_14_20_points_allowed
                elif points_allowed <= 27:
                    pa_points = scoring_config.def_21_27_points_allowed
                elif points_allowed <= 34:
                    pa_points = scoring_config.def_28_34_points_allowed
                else:
                    pa_points = scoring_config.def_35_plus_points_allowed
                
                points_breakdown['points_allowed'] = pa_points
                total_points += pa_points
            
            # Fumbles (all positions)
            if stats.get('fumbles_lost'):
                fumble_points = stats['fumbles_lost'] * scoring_config.fumble_lost_points
                points_breakdown['fumbles_lost'] = fumble_points
                total_points += fumble_points
            
            # Advanced scoring (if enabled)
            if scoring_config.target_points > 0 and stats.get('receiving_stats', {}).get('targets'):
                target_points = stats['receiving_stats']['targets'] * scoring_config.target_points
                points_breakdown['targets'] = target_points
                total_points += target_points
            
            if scoring_config.carry_points > 0 and stats.get('rushing_stats', {}).get('attempts'):
                carry_points = stats['rushing_stats']['attempts'] * scoring_config.carry_points
                points_breakdown['carries'] = carry_points
                total_points += carry_points
            
            return {
                "total_points": round(total_points, 2),
                "points_breakdown": points_breakdown,
                "scoring_type": scoring_config.scoring_type.value,
                "league_scoring_id": scoring_config.id
            }
            
        except Exception as e:
            logger.error(f"Error calculating fantasy points: {str(e)}")
            return {
                "total_points": 0.0,
                "points_breakdown": {},
                "error": str(e)
            }
    
    def get_scoring_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Get predefined scoring preset"""
        preset = self.db.query(ScoringPreset).filter(
            ScoringPreset.name == preset_name
        ).first()
        
        return preset.scoring_settings if preset else None
    
    def create_default_presets(self):
        """Create default scoring presets if they don't exist"""
        default_presets = [
            {
                "name": "ESPN Standard",
                "description": "Default ESPN league scoring",
                "scoring_type": "STANDARD",
                "settings": {
                    "reception_points": 0.0,
                    "passing_yards_per_point": 25.0,
                    "passing_td_points": 4.0,
                    "rushing_yards_per_point": 10.0,
                    "rushing_td_points": 6.0,
                    "receiving_yards_per_point": 10.0,
                    "receiving_td_points": 6.0
                }
            },
            {
                "name": "ESPN PPR",
                "description": "ESPN PPR league scoring",
                "scoring_type": "PPR",
                "settings": {
                    "reception_points": 1.0,
                    "passing_yards_per_point": 25.0,
                    "passing_td_points": 4.0,
                    "rushing_yards_per_point": 10.0,
                    "rushing_td_points": 6.0,
                    "receiving_yards_per_point": 10.0,
                    "receiving_td_points": 6.0
                }
            },
            {
                "name": "Yahoo Standard",
                "description": "Default Yahoo league scoring",
                "scoring_type": "STANDARD",
                "settings": {
                    "reception_points": 0.0,
                    "passing_yards_per_point": 25.0,
                    "passing_td_points": 4.0,
                    "passing_int_points": -1.0,
                    "rushing_yards_per_point": 10.0,
                    "rushing_td_points": 6.0,
                    "receiving_yards_per_point": 10.0,
                    "receiving_td_points": 6.0
                }
            },
            {
                "name": "Sleeper PPR",
                "description": "Sleeper PPR league scoring with bonuses",
                "scoring_type": "PPR",
                "settings": {
                    "reception_points": 1.0,
                    "passing_yards_per_point": 25.0,
                    "passing_td_points": 4.0,
                    "passing_300_yard_bonus": 3.0,
                    "rushing_yards_per_point": 10.0,
                    "rushing_td_points": 6.0,
                    "rushing_100_yard_bonus": 3.0,
                    "receiving_yards_per_point": 10.0,
                    "receiving_td_points": 6.0,
                    "receiving_100_yard_bonus": 3.0
                }
            }
        ]
        
        for preset_data in default_presets:
            existing = self.db.query(ScoringPreset).filter(
                ScoringPreset.name == preset_data["name"]
            ).first()
            
            if not existing:
                preset = ScoringPreset(
                    name=preset_data["name"],
                    description=preset_data["description"],
                    scoring_type=preset_data["scoring_type"],
                    scoring_settings=preset_data["settings"],
                    is_default=True
                )
                self.db.add(preset)
        
        self.db.commit()
    
    def recalculate_player_points_for_league(
        self, 
        league_scoring_id: int, 
        player_id: Optional[int] = None,
        season: int = 2024
    ) -> Dict[str, Any]:
        """
        Recalculate fantasy points for all players (or specific player) 
        using league-specific scoring
        """
        try:
            scoring_config = self.db.query(LeagueScoring).filter(
                LeagueScoring.id == league_scoring_id
            ).first()
            
            if not scoring_config:
                return {"error": "Scoring configuration not found"}
            
            # Get player performances to recalculate
            query = self.db.query(PlayerHistoricalPerformance).filter(
                PlayerHistoricalPerformance.season == season
            )
            
            if player_id:
                query = query.filter(PlayerHistoricalPerformance.player_id == player_id)
            
            performances = query.all()
            
            recalculated_count = 0
            
            for performance in performances:
                # Get player info for position-specific scoring
                player = self.db.query(Player).filter(Player.id == performance.player_id).first()
                if not player:
                    continue
                
                # Prepare stats for calculation
                stats = {
                    'passing_stats': performance.passing_stats,
                    'rushing_stats': performance.rushing_stats,
                    'receiving_stats': performance.receiving_stats,
                    'defensive_stats': performance.defensive_stats,
                    'kicking_stats': performance.kicking_stats,
                    'fumbles_lost': 0  # Add if available in your data
                }
                
                # Calculate points
                calculation = self.calculate_fantasy_points(
                    stats, scoring_config, player.position.value if player.position else "UNKNOWN"
                )
                
                # Store or update calculation
                existing_calc = self.db.query(PlayerScoringCalculation).filter(
                    and_(
                        PlayerScoringCalculation.player_id == performance.player_id,
                        PlayerScoringCalculation.league_scoring_id == league_scoring_id,
                        PlayerScoringCalculation.season == performance.season,
                        PlayerScoringCalculation.week == performance.week
                    )
                ).first()
                
                if existing_calc:
                    existing_calc.calculated_points = calculation['total_points']
                    existing_calc.points_breakdown = calculation['points_breakdown']
                    existing_calc.ppr_difference = calculation['total_points'] - (performance.fantasy_points_ppr or 0)
                    existing_calc.standard_difference = calculation['total_points'] - (performance.fantasy_points_standard or 0)
                else:
                    new_calc = PlayerScoringCalculation(
                        player_id=performance.player_id,
                        league_scoring_id=league_scoring_id,
                        season=performance.season,
                        week=performance.week,
                        raw_stats=stats,
                        calculated_points=calculation['total_points'],
                        points_breakdown=calculation['points_breakdown'],
                        ppr_difference=calculation['total_points'] - (performance.fantasy_points_ppr or 0),
                        standard_difference=calculation['total_points'] - (performance.fantasy_points_standard or 0)
                    )
                    self.db.add(new_calc)
                
                recalculated_count += 1
            
            self.db.commit()
            
            return {
                "success": True,
                "recalculated_performances": recalculated_count,
                "league_scoring_id": league_scoring_id,
                "season": season
            }
            
        except Exception as e:
            logger.error(f"Error recalculating points: {str(e)}")
            self.db.rollback()
            return {"error": f"Recalculation failed: {str(e)}"}
    
    def get_player_points_with_custom_scoring(
        self, 
        player_id: int, 
        league_scoring_id: int,
        season: int = 2024
    ) -> Dict[str, Any]:
        """Get player's fantasy points calculated with specific league scoring"""
        
        try:
            calculations = self.db.query(PlayerScoringCalculation).filter(
                and_(
                    PlayerScoringCalculation.player_id == player_id,
                    PlayerScoringCalculation.league_scoring_id == league_scoring_id,
                    PlayerScoringCalculation.season == season
                )
            ).order_by(PlayerScoringCalculation.week).all()
            
            if not calculations:
                return {"error": "No calculations found for this player/league combination"}
            
            # Calculate season totals
            total_points = sum(calc.calculated_points for calc in calculations)
            games_played = len(calculations)
            avg_points = total_points / games_played if games_played > 0 else 0
            
            # Get breakdown by week
            weekly_breakdown = []
            for calc in calculations:
                weekly_breakdown.append({
                    "week": calc.week,
                    "points": calc.calculated_points,
                    "breakdown": calc.points_breakdown,
                    "ppr_difference": calc.ppr_difference,
                    "standard_difference": calc.standard_difference
                })
            
            return {
                "player_id": player_id,
                "season": season,
                "total_points": round(total_points, 2),
                "games_played": games_played,
                "avg_points_per_game": round(avg_points, 2),
                "weekly_breakdown": weekly_breakdown,
                "scoring_advantages": {
                    "vs_ppr": round(sum(calc.ppr_difference or 0 for calc in calculations), 2),
                    "vs_standard": round(sum(calc.standard_difference or 0 for calc in calculations), 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting custom scoring points: {str(e)}")
            return {"error": f"Failed to get custom scoring: {str(e)}"}
    
    def compare_scoring_systems(
        self, 
        player_id: int, 
        scoring_configs: List[int],
        season: int = 2024
    ) -> Dict[str, Any]:
        """Compare player performance across different scoring systems"""
        
        try:
            comparisons = {}
            
            for config_id in scoring_configs:
                config = self.db.query(LeagueScoring).filter(LeagueScoring.id == config_id).first()
                if not config:
                    continue
                
                player_points = self.get_player_points_with_custom_scoring(
                    player_id, config_id, season
                )
                
                if "error" not in player_points:
                    comparisons[f"config_{config_id}"] = {
                        "scoring_type": config.scoring_type.value,
                        "total_points": player_points["total_points"],
                        "avg_per_game": player_points["avg_points_per_game"],
                        "games_played": player_points["games_played"]
                    }
            
            # Calculate relative rankings
            if len(comparisons) > 1:
                sorted_configs = sorted(
                    comparisons.items(), 
                    key=lambda x: x[1]["total_points"], 
                    reverse=True
                )
                
                for i, (config_key, data) in enumerate(sorted_configs):
                    comparisons[config_key]["rank"] = i + 1
                    comparisons[config_key]["percentile"] = (len(sorted_configs) - i) / len(sorted_configs) * 100
            
            return {
                "player_id": player_id,
                "season": season,
                "scoring_comparisons": comparisons,
                "best_scoring_system": max(comparisons.keys(), key=lambda k: comparisons[k]["total_points"]) if comparisons else None
            }
            
        except Exception as e:
            logger.error(f"Error comparing scoring systems: {str(e)}")
            return {"error": f"Scoring comparison failed: {str(e)}"}
    
    def get_league_scoring_impact(self, league_scoring_id: int) -> Dict[str, Any]:
        """Analyze how league scoring affects player values"""
        
        try:
            scoring_config = self.db.query(LeagueScoring).filter(
                LeagueScoring.id == league_scoring_id
            ).first()
            
            if not scoring_config:
                return {"error": "Scoring configuration not found"}
            
            # Analyze scoring biases
            analysis = {
                "scoring_type": scoring_config.scoring_type.value,
                "biases": [],
                "advantages": {},
                "recommendations": []
            }
            
            # Reception scoring bias
            if scoring_config.reception_points > 0:
                analysis["biases"].append("Favors pass-catching backs and slot receivers")
                analysis["advantages"]["WR"] = f"+{scoring_config.reception_points} per reception"
                analysis["advantages"]["TE"] = f"+{scoring_config.reception_points} per reception"
                analysis["recommendations"].append("Target high-reception volume players")
            
            # Yardage bonuses
            if scoring_config.passing_300_yard_bonus > 0:
                analysis["advantages"]["QB"] = f"+{scoring_config.passing_300_yard_bonus} for 300+ yards"
                analysis["recommendations"].append("Elite QBs get extra value from yardage bonuses")
            
            if scoring_config.rushing_100_yard_bonus > 0 or scoring_config.receiving_100_yard_bonus > 0:
                analysis["recommendations"].append("Big-play ability becomes more valuable")
            
            # Penalty analysis
            if scoring_config.passing_int_points < -1:
                analysis["biases"].append("Heavily penalizes QB turnovers")
                analysis["recommendations"].append("Prioritize low-interception QBs")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing league scoring: {str(e)}")
            return {"error": f"Scoring analysis failed: {str(e)}"}