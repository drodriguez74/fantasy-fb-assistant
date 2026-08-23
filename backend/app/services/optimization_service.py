"""
Fantasy Football Optimization Service

This service provides lineup optimization, roster construction,
and portfolio optimization for fantasy football.
"""

import pulp
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.player import Player, Position
from app.models.historical_performance import PlayerHistoricalPerformance, PlayerSeasonSummary

logger = logging.getLogger(__name__)


class OptimizationService:
    """
    Optimization algorithms for fantasy football:
    - Lineup optimization (maximize points within salary cap)
    - Roster construction optimization
    - Risk-adjusted portfolio optimization
    - Multi-objective optimization (points, consistency, upside)
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def optimize_lineup(
        self,
        players: List[Dict[str, Any]],
        salary_cap: int = 50000,
        lineup_constraints: Optional[Dict[str, int]] = None,
        optimization_type: str = "maximize_points"
    ) -> Dict[str, Any]:
        """
        Optimize fantasy lineup using linear programming
        
        Args:
            players: List of player dictionaries with projected_points, salary, position
            salary_cap: Total salary budget
            lineup_constraints: Position requirements (e.g., {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "DEF": 1})
            optimization_type: 'maximize_points', 'risk_adjusted', 'ceiling_optimizer'
        """
        try:
            if not lineup_constraints:
                lineup_constraints = {
                    "QB": 1, "RB": 2, "WR": 3, "TE": 1, 
                    "FLEX": 1, "DEF": 1, "K": 1
                }
            
            # Create optimization problem
            prob = pulp.LpProblem("Fantasy_Lineup_Optimization", pulp.LpMaximize)
            
            # Decision variables (binary: 1 if player selected, 0 otherwise)
            player_vars = {}
            for i, player in enumerate(players):
                player_vars[i] = pulp.LpVariable(f"player_{i}", cat='Binary')
            
            # Objective function
            if optimization_type == "maximize_points":
                objective = pulp.lpSum([
                    player_vars[i] * player.get('projected_points', 0) 
                    for i, player in enumerate(players)
                ])
            elif optimization_type == "risk_adjusted":
                # Maximize points while minimizing variance
                objective = pulp.lpSum([
                    player_vars[i] * (
                        player.get('projected_points', 0) - 
                        0.1 * player.get('variance', 0)  # Risk penalty
                    )
                    for i, player in enumerate(players)
                ])
            elif optimization_type == "ceiling_optimizer":
                # Optimize for upside potential
                objective = pulp.lpSum([
                    player_vars[i] * player.get('ceiling', player.get('projected_points', 0))
                    for i, player in enumerate(players)
                ])
            else:
                objective = pulp.lpSum([
                    player_vars[i] * player.get('projected_points', 0) 
                    for i, player in enumerate(players)
                ])
            
            prob += objective
            
            # Salary constraint
            prob += pulp.lpSum([
                player_vars[i] * player.get('salary', 0) 
                for i, player in enumerate(players)
            ]) <= salary_cap
            
            # Position constraints
            position_groups = {}
            for position in lineup_constraints.keys():
                position_groups[position] = [
                    i for i, player in enumerate(players) 
                    if player.get('position') == position or 
                    (position == 'FLEX' and player.get('position') in ['RB', 'WR', 'TE'])
                ]
            
            flex_base_positions = {'RB', 'WR', 'TE'}
            has_flex = lineup_constraints.get('FLEX', 0) > 0

            for position, required_count in lineup_constraints.items():
                if position == 'FLEX':
                    # Handled below together with the base RB/WR/TE requirements via a
                    # single combined constraint, so the same player pool isn't
                    # double-constrained (individual == plus a separate FLEX >= over the
                    # same variables is infeasible whenever a FLEX slot is requested).
                    continue
                if not position_groups.get(position):
                    continue
                if has_flex and position in flex_base_positions:
                    # Relax to a floor: exactly how many extra RB/WR/TE players fill the
                    # FLEX slot(s) is decided by the combined constraint below.
                    prob += pulp.lpSum([
                        player_vars[i] for i in position_groups[position]
                    ]) >= required_count
                else:
                    prob += pulp.lpSum([
                        player_vars[i] for i in position_groups[position]
                    ]) == required_count

            if has_flex and position_groups.get('FLEX'):
                # Exactly RB_required + WR_required + TE_required + FLEX_required players
                # are drawn from the combined RB/WR/TE pool. Together with the >= floors
                # above (each base position still gets at least its own requirement),
                # this pins down the FLEX slot(s) without any player occupying two slots.
                total_flex_pool_required = (
                    lineup_constraints.get('RB', 0) + lineup_constraints.get('WR', 0) +
                    lineup_constraints.get('TE', 0) + lineup_constraints.get('FLEX', 0)
                )
                prob += pulp.lpSum([
                    player_vars[i] for i in position_groups['FLEX']
                ]) == total_flex_pool_required
            
            # Total lineup size constraint
            total_positions = sum(lineup_constraints.values())
            prob += pulp.lpSum([player_vars[i] for i in range(len(players))]) == total_positions
            
            # Solve optimization
            prob.solve(pulp.PULP_CBC_CMD(msg=0))
            
            if prob.status != pulp.LpStatusOptimal:
                return {"error": "No optimal solution found", "status": pulp.LpStatus[prob.status]}
            
            # Extract results
            selected_players = []
            total_salary = 0
            total_points = 0
            
            for i, player in enumerate(players):
                if player_vars[i].value() == 1:
                    selected_players.append({
                        **player,
                        "selected": True
                    })
                    total_salary += player.get('salary', 0)
                    total_points += player.get('projected_points', 0)
            
            return {
                "optimization_type": optimization_type,
                "lineup_constraints": lineup_constraints,
                "selected_players": selected_players,
                "total_salary": total_salary,
                "salary_cap": salary_cap,
                "salary_remaining": salary_cap - total_salary,
                "projected_points": total_points,
                "objective_value": prob.objective.value(),
                "lineup_size": len(selected_players),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error optimizing lineup: {str(e)}")
            return {"error": f"Lineup optimization failed: {str(e)}"}
    
    async def optimize_multi_lineup(
        self,
        players: List[Dict[str, Any]],
        num_lineups: int = 5,
        salary_cap: int = 50000,
        diversity_constraint: float = 0.7  # Maximum overlap between lineups
    ) -> Dict[str, Any]:
        """
        Generate multiple optimized lineups with diversity constraints
        """
        try:
            lineups = []
            used_players = set()
            
            for lineup_num in range(num_lineups):
                # Adjust player pool based on previous selections
                available_players = []
                for player in players:
                    player_id = player.get('player_id', player.get('id'))
                    
                    # Reduce appeal of heavily used players
                    usage_penalty = used_players.count(player_id) * 0.1
                    adjusted_player = {
                        **player,
                        'projected_points': player.get('projected_points', 0) - usage_penalty
                    }
                    available_players.append(adjusted_player)
                
                # Optimize this lineup
                lineup_result = await self.optimize_lineup(
                    available_players, 
                    salary_cap=salary_cap,
                    optimization_type="maximize_points"
                )
                
                if "error" not in lineup_result:
                    lineups.append({
                        **lineup_result,
                        "lineup_number": lineup_num + 1
                    })
                    
                    # Track player usage
                    for player in lineup_result.get('selected_players', []):
                        player_id = player.get('player_id', player.get('id'))
                        used_players.add(player_id)
            
            # Calculate diversity metrics
            if len(lineups) > 1:
                diversity_stats = self._calculate_lineup_diversity(lineups)
            else:
                diversity_stats = {"avg_overlap": 0, "min_overlap": 0, "max_overlap": 0}
            
            return {
                "num_lineups_requested": num_lineups,
                "num_lineups_generated": len(lineups),
                "lineups": lineups,
                "diversity_stats": diversity_stats,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating multiple lineups: {str(e)}")
            return {"error": f"Multi-lineup optimization failed: {str(e)}"}
    
    def _calculate_lineup_diversity(self, lineups: List[Dict]) -> Dict[str, float]:
        """Calculate diversity metrics between lineups"""
        overlaps = []
        
        for i in range(len(lineups)):
            for j in range(i + 1, len(lineups)):
                lineup1_players = {p.get('player_id', p.get('id')) for p in lineups[i].get('selected_players', [])}
                lineup2_players = {p.get('player_id', p.get('id')) for p in lineups[j].get('selected_players', [])}
                
                overlap = len(lineup1_players.intersection(lineup2_players)) / len(lineup1_players)
                overlaps.append(overlap)
        
        if overlaps:
            return {
                "avg_overlap": float(np.mean(overlaps)),
                "min_overlap": float(np.min(overlaps)),
                "max_overlap": float(np.max(overlaps))
            }
        else:
            return {"avg_overlap": 0, "min_overlap": 0, "max_overlap": 0}
    
    async def optimize_season_roster(
        self,
        available_players: List[Dict[str, Any]],
        roster_constraints: Optional[Dict[str, int]] = None,
        budget_constraint: Optional[int] = None,
        target_weeks: int = 17
    ) -> Dict[str, Any]:
        """
        Optimize full season roster construction
        """
        try:
            if not roster_constraints:
                roster_constraints = {
                    "QB": 2, "RB": 4, "WR": 4, "TE": 2, "DEF": 2, "K": 1
                }
            
            # Create optimization problem
            prob = pulp.LpProblem("Season_Roster_Optimization", pulp.LpMaximize)
            
            # Decision variables
            player_vars = {}
            for i, player in enumerate(available_players):
                player_vars[i] = pulp.LpVariable(f"player_{i}", cat='Binary')
            
            # Objective: Maximize season-long value
            objective = pulp.lpSum([
                player_vars[i] * self._calculate_season_value(player) 
                for i, player in enumerate(available_players)
            ])
            prob += objective
            
            # Budget constraint (if applicable)
            if budget_constraint:
                prob += pulp.lpSum([
                    player_vars[i] * player.get('salary', 0) 
                    for i, player in enumerate(available_players)
                ]) <= budget_constraint
            
            # Position constraints
            for position, max_count in roster_constraints.items():
                position_players = [
                    i for i, player in enumerate(available_players) 
                    if player.get('position') == position
                ]
                if position_players:
                    prob += pulp.lpSum([
                        player_vars[i] for i in position_players
                    ]) <= max_count
            
            # Solve optimization
            prob.solve(pulp.PULP_CBC_CMD(msg=0))
            
            if prob.status != pulp.LpStatusOptimal:
                return {"error": "No optimal solution found", "status": pulp.LpStatus[prob.status]}
            
            # Extract results
            selected_players = []
            total_cost = 0
            
            for i, player in enumerate(available_players):
                if player_vars[i].value() == 1:
                    selected_players.append({
                        **player,
                        "season_value": self._calculate_season_value(player)
                    })
                    total_cost += player.get('salary', 0)
            
            # Analyze roster construction
            position_counts = {}
            for player in selected_players:
                pos = player.get('position', 'Unknown')
                position_counts[pos] = position_counts.get(pos, 0) + 1
            
            return {
                "roster_constraints": roster_constraints,
                "selected_players": selected_players,
                "position_distribution": position_counts,
                "total_cost": total_cost,
                "budget_constraint": budget_constraint,
                "budget_remaining": (budget_constraint - total_cost) if budget_constraint else None,
                "roster_size": len(selected_players),
                "projected_season_value": prob.objective.value(),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error optimizing season roster: {str(e)}")
            return {"error": f"Season roster optimization failed: {str(e)}"}
    
    def _calculate_season_value(self, player: Dict[str, Any]) -> float:
        """Calculate a player's season-long value"""
        base_points = player.get('projected_points', 0)
        consistency = player.get('consistency_score', 0.5)
        games_played = player.get('games_played', 16)
        
        # Season value formula
        season_value = (base_points * games_played * (1 + consistency)) / 16
        
        # Apply position scarcity multiplier
        position_multipliers = {
            'QB': 1.0, 'RB': 1.2, 'WR': 1.1, 'TE': 1.3, 'DEF': 0.8, 'K': 0.6
        }
        position = player.get('position', 'Unknown')
        multiplier = position_multipliers.get(position, 1.0)
        
        return season_value * multiplier
    
    async def portfolio_risk_analysis(
        self,
        roster_players: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze risk metrics for a fantasy roster
        """
        try:
            if len(roster_players) == 0:
                return {"error": "No players provided for risk analysis"}
            
            # Calculate portfolio metrics
            total_projected = sum(p.get('projected_points', 0) for p in roster_players)
            
            # Variance calculation (simplified)
            variances = []
            correlations = []
            
            for player in roster_players:
                variance = player.get('variance', 0) or player.get('projected_points', 0) * 0.1
                variances.append(variance)
            
            portfolio_variance = sum(variances)  # Simplified - assumes independence
            portfolio_std = np.sqrt(portfolio_variance)
            
            # Risk-adjusted metrics
            sharpe_ratio = total_projected / portfolio_std if portfolio_std > 0 else 0
            
            # Position concentration risk
            position_exposure = {}
            for player in roster_players:
                pos = player.get('position', 'Unknown')
                points = player.get('projected_points', 0)
                position_exposure[pos] = position_exposure.get(pos, 0) + points
            
            total_exposure = sum(position_exposure.values())
            position_weights = {
                pos: exposure / total_exposure 
                for pos, exposure in position_exposure.items()
            } if total_exposure > 0 else {}
            
            # Calculate concentration risk (Herfindahl index)
            concentration_risk = sum(weight ** 2 for weight in position_weights.values())
            
            # Injury risk assessment
            injury_risk_score = 0
            for player in roster_players:
                risk_level = player.get('risk_level', 'MEDIUM')
                if risk_level == 'HIGH':
                    injury_risk_score += 3
                elif risk_level == 'MEDIUM':
                    injury_risk_score += 1
            
            injury_risk_score = injury_risk_score / len(roster_players)  # Normalize
            
            return {
                "portfolio_metrics": {
                    "total_projected_points": total_projected,
                    "portfolio_variance": portfolio_variance,
                    "portfolio_std_dev": portfolio_std,
                    "sharpe_ratio": sharpe_ratio
                },
                "risk_metrics": {
                    "concentration_risk": concentration_risk,
                    "position_weights": position_weights,
                    "injury_risk_score": injury_risk_score,
                    "diversification_score": 1 - concentration_risk  # Higher is better
                },
                "roster_size": len(roster_players),
                "risk_level": self._classify_risk_level(concentration_risk, injury_risk_score),
                "recommendations": self._generate_risk_recommendations(
                    concentration_risk, injury_risk_score, position_weights
                ),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing portfolio risk: {str(e)}")
            return {"error": f"Risk analysis failed: {str(e)}"}
    
    def _classify_risk_level(self, concentration_risk: float, injury_risk: float) -> str:
        """Classify overall portfolio risk level"""
        risk_score = concentration_risk + injury_risk
        
        if risk_score > 2.0:
            return "HIGH"
        elif risk_score > 1.0:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_risk_recommendations(
        self, 
        concentration_risk: float, 
        injury_risk: float, 
        position_weights: Dict[str, float]
    ) -> List[str]:
        """Generate recommendations to reduce portfolio risk"""
        recommendations = []
        
        if concentration_risk > 0.3:
            recommendations.append("Consider diversifying across more positions to reduce concentration risk")
        
        if injury_risk > 1.5:
            recommendations.append("High injury risk detected - consider backup players or safer alternatives")
        
        # Check for position over-concentration
        for position, weight in position_weights.items():
            if weight > 0.4:
                recommendations.append(f"High exposure to {position} position ({weight:.1%}) - consider rebalancing")
        
        if not recommendations:
            recommendations.append("Portfolio risk levels appear well-balanced")
        
        return recommendations