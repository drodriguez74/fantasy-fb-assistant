from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models.player import Player, Position, InjuryStatus, RiskLevel
from app.services.sleeper_service import sleeper_service
from app.services.ai_service import ai_service
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PlayerDataService:
    def __init__(self, db: Session):
        self.db = db

    async def sync_player_data(self) -> Dict[str, Any]:
        """Sync player data from external sources and enhance with analytics"""
        try:
            # Get all players from Sleeper
            sleeper_players = await sleeper_service.get_all_players()
            
            if "error" in sleeper_players:
                return {"error": sleeper_players["error"]}
            
            updated_count = 0
            new_count = 0
            
            for player_id, player_data in sleeper_players.items():
                if not isinstance(player_data, dict):
                    continue
                    
                # Find or create player
                player = self.db.query(Player).filter(Player.sleeper_id == player_id).first()
                
                if player:
                    # Update existing player
                    await self._update_player_from_sleeper(player, player_data)
                    updated_count += 1
                else:
                    # Create new player
                    await self._create_player_from_sleeper(player_id, player_data)
                    new_count += 1
                    
                # Commit in batches
                if (updated_count + new_count) % 50 == 0:
                    self.db.commit()
            
            self.db.commit()
            
            return {
                "success": True,
                "updated_players": updated_count,
                "new_players": new_count,
                "total_processed": updated_count + new_count
            }
            
        except Exception as e:
            logger.error(f"Error syncing player data: {str(e)}")
            return {"error": str(e)}

    async def _create_player_from_sleeper(self, player_id: str, sleeper_data: Dict) -> Optional[Player]:
        """Create a new player from Sleeper data"""
        try:
            # Map position
            position_str = sleeper_data.get("position", "").upper()
            if position_str not in [p.value for p in Position]:
                logger.warning(f"Unknown position {position_str} for player {player_id}")
                return None
            
            position = Position(position_str)
            
            # Create player
            player = Player(
                name=sleeper_data.get("full_name", ""),
                first_name=sleeper_data.get("first_name", ""),
                last_name=sleeper_data.get("last_name", ""),
                team=sleeper_data.get("team", ""),
                position=position,
                sleeper_id=player_id,
                espn_id=str(sleeper_data.get("espn_id", "")),
                yahoo_id=str(sleeper_data.get("yahoo_id", "")),
                age=sleeper_data.get("age"),
                height=sleeper_data.get("height", ""),
                weight=sleeper_data.get("weight"),
                college=sleeper_data.get("college", ""),
                years_exp=sleeper_data.get("years_exp", 0),
                jersey_number=sleeper_data.get("number"),
                injury_status=self._map_injury_status(sleeper_data.get("injury_status")),
                injury_body_part=sleeper_data.get("injury_body_part"),
                depth_chart_order=sleeper_data.get("depth_chart_order"),
                is_rookie=sleeper_data.get("years_exp", 0) == 0
            )
            
            self.db.add(player)
            return player
            
        except Exception as e:
            logger.error(f"Error creating player {player_id}: {str(e)}")
            return None

    async def _update_player_from_sleeper(self, player: Player, sleeper_data: Dict):
        """Update existing player with Sleeper data"""
        try:
            # Update basic info
            player.name = sleeper_data.get("full_name", player.name)
            player.first_name = sleeper_data.get("first_name", player.first_name)
            player.last_name = sleeper_data.get("last_name", player.last_name)
            player.team = sleeper_data.get("team", player.team)
            player.age = sleeper_data.get("age", player.age)
            player.height = sleeper_data.get("height", player.height)
            player.weight = sleeper_data.get("weight", player.weight)
            player.college = sleeper_data.get("college", player.college)
            player.years_exp = sleeper_data.get("years_exp", player.years_exp)
            player.jersey_number = sleeper_data.get("number", player.jersey_number)
            
            # Update injury info
            new_injury_status = self._map_injury_status(sleeper_data.get("injury_status"))
            if new_injury_status != player.injury_status:
                player.injury_status = new_injury_status
                player.injury_updated_at = datetime.utcnow()
            
            player.injury_body_part = sleeper_data.get("injury_body_part", player.injury_body_part)
            player.depth_chart_order = sleeper_data.get("depth_chart_order", player.depth_chart_order)
            
            # Update trending info if available
            if "trending_count" in sleeper_data:
                player.trending_count = sleeper_data["trending_count"]
                
            player.updated_at = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error updating player {player.sleeper_id}: {str(e)}")

    def _map_injury_status(self, sleeper_status: str) -> InjuryStatus:
        """Map Sleeper injury status to our enum"""
        if not sleeper_status:
            return InjuryStatus.HEALTHY
            
        status_mapping = {
            "Healthy": InjuryStatus.HEALTHY,
            "Questionable": InjuryStatus.QUESTIONABLE,
            "Doubtful": InjuryStatus.DOUBTFUL,
            "Out": InjuryStatus.OUT,
            "IR": InjuryStatus.IR,
            "PUP": InjuryStatus.PUP,
            "Suspended": InjuryStatus.SUSPENDED
        }
        
        return status_mapping.get(sleeper_status, InjuryStatus.HEALTHY)

    async def calculate_advanced_metrics(self, player_id: int) -> Dict[str, Any]:
        """Calculate advanced metrics for a player"""
        try:
            player = self.db.query(Player).filter(Player.id == player_id).first()
            if not player:
                return {"error": "Player not found"}
            
            # Calculate ceiling/floor scores based on consistency
            if player.projected_points:
                consistency = player.consistency_rating or 5.0
                variance = (10 - consistency) * 0.1  # Higher consistency = lower variance
                
                player.ceiling_score = player.projected_points * (1 + variance)
                player.floor_score = player.projected_points * (1 - variance * 0.5)
            
            # Calculate tier based on position rank
            if player.position_rank:
                if player.position_rank <= 5:
                    player.tier = 1
                elif player.position_rank <= 12:
                    player.tier = 2
                elif player.position_rank <= 24:
                    player.tier = 3
                elif player.position_rank <= 36:
                    player.tier = 4
                else:
                    player.tier = 5
            
            # Determine risk level
            risk_factors = 0
            if player.injury_status != InjuryStatus.HEALTHY:
                risk_factors += 2
            if player.age and player.age > 30:
                risk_factors += 1
            if player.years_exp and player.years_exp < 2:
                risk_factors += 1
                
            if risk_factors >= 3:
                player.risk_level = RiskLevel.HIGH
            elif risk_factors >= 1:
                player.risk_level = RiskLevel.MEDIUM
            else:
                player.risk_level = RiskLevel.LOW
            
            self.db.commit()
            
            return {
                "success": True,
                "ceiling_score": player.ceiling_score,
                "floor_score": player.floor_score,
                "tier": player.tier,
                "risk_level": player.risk_level.value
            }
            
        except Exception as e:
            logger.error(f"Error calculating metrics for player {player_id}: {str(e)}")
            return {"error": str(e)}

    async def generate_enhanced_analysis(self, player_id: int) -> Dict[str, Any]:
        """Generate enhanced AI analysis using the new data"""
        try:
            player = self.db.query(Player).filter(Player.id == player_id).first()
            if not player:
                return {"error": "Player not found"}
            
            # Prepare player data for AI analysis
            player_data = {
                "position": player.position.value,
                "team": player.team,
                "age": player.age,
                "years_exp": player.years_exp,
                "injury_status": player.injury_status.value if player.injury_status else "HEALTHY",
                "projected_points": player.projected_points,
                "target_share": player.target_share,
                "snap_count_percentage": player.snap_count_percentage,
                "depth_chart_order": player.depth_chart_order,
                "trending_direction": player.trending_direction,
                "season_stats": player.season_stats,
                "last_game_stats": player.last_game_stats
            }
            
            # Call AI service with correct parameters
            analysis = await ai_service.generate_player_analysis(
                player_name=player.name,
                player_data=player_data,
                historical_data=None  # Could be enhanced later with historical data
            )
            
            # Update player with new analysis (AI service returns string directly)
            player.ai_analysis = analysis if analysis else "Analysis not available"
            player.updated_at = datetime.utcnow()
            self.db.commit()
            
            return {
                "success": True,
                "analysis": analysis if analysis else "Analysis not available",
                "updated_at": player.updated_at
            }
            
        except Exception as e:
            logger.error(f"Error generating enhanced analysis for player {player_id}: {str(e)}")
            return {"error": str(e)}

    def get_players_by_criteria(self, 
                               position: Optional[str] = None,
                               team: Optional[str] = None,
                               injury_status: Optional[str] = None,
                               min_projected_points: Optional[float] = None,
                               max_risk_level: Optional[str] = None,
                               page: int = 1,
                               page_size: int = 50) -> Dict[str, Any]:
        """Get players filtered by various criteria with pagination"""
        try:
            # Validate pagination parameters
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 50
            if page_size > 200:  # Limit max page size to prevent performance issues
                page_size = 200
            
            query = self.db.query(Player)
            
            if position:
                query = query.filter(Player.position == Position(position.upper()))
            
            if team:
                query = query.filter(Player.team == team.upper())
                
            if injury_status:
                query = query.filter(Player.injury_status == InjuryStatus(injury_status.upper()))
                
            if min_projected_points:
                query = query.filter(Player.projected_points >= min_projected_points)
                
            if max_risk_level:
                risk_levels = {
                    "LOW": [RiskLevel.LOW],
                    "MEDIUM": [RiskLevel.LOW, RiskLevel.MEDIUM],
                    "HIGH": [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
                }
                query = query.filter(Player.risk_level.in_(risk_levels.get(max_risk_level.upper(), [RiskLevel.LOW])))
            
            # Order by projected points descending
            query = query.order_by(Player.projected_points.desc().nullslast())
            
            # Get total count before pagination
            total_count = query.count()
            
            # Apply pagination
            offset = (page - 1) * page_size
            players = query.offset(offset).limit(page_size).all()
            
            # Calculate pagination metadata
            total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
            has_next = page < total_pages
            has_previous = page > 1
            
            return {
                "players": players,
                "pagination": {
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "current_page": page,
                    "page_size": page_size,
                    "has_next": has_next,
                    "has_previous": has_previous,
                    "next_page": page + 1 if has_next else None,
                    "previous_page": page - 1 if has_previous else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error filtering players: {str(e)}")
            return {
                "players": [],
                "pagination": {
                    "total_count": 0,
                    "total_pages": 0,
                    "current_page": page,
                    "page_size": page_size,
                    "has_next": False,
                    "has_previous": False,
                    "next_page": None,
                    "previous_page": None
                }
            }

    def get_trending_players(self, direction: str = "UP", limit: int = 20) -> List[Player]:
        """Get trending players based on add/drop activity"""
        try:
            query = self.db.query(Player)
            
            if direction.upper() == "UP":
                query = query.filter(Player.trending_count > 0)
                query = query.order_by(Player.trending_count.desc())
            else:
                query = query.filter(Player.trending_count < 0)
                query = query.order_by(Player.trending_count.asc())
                
            return query.limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting trending players: {str(e)}")
            return []

    def get_injury_report(self) -> List[Player]:
        """Get all players with injury concerns"""
        try:
            return self.db.query(Player).filter(
                Player.injury_status != InjuryStatus.HEALTHY
            ).order_by(
                Player.injury_updated_at.desc().nullslast(),
                Player.projected_points.desc().nullslast()
            ).all()
            
        except Exception as e:
            logger.error(f"Error getting injury report: {str(e)}")
            return []