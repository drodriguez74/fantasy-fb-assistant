from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from app.models.player import Player
from app.models.historical_performance import (
    PlayerHistoricalPerformance, 
    PlayerSeasonSummary, 
    PlayerTrend, 
    MatchupHistory,
    FantasyLeagueHistory,
    PerformanceType,
    GameLocation
)
from app.services.sleeper_service import sleeper_service
from app.services.yahoo_service import yahoo_service
from app.services.ai_service import ai_service
from datetime import datetime, timedelta
import logging
import json
import statistics
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

class HistoricalDataService:
    def __init__(self, db: Session):
        self.db = db

    async def sync_historical_data(self, seasons: List[int] = None) -> Dict[str, Any]:
        """Sync historical performance data from external sources"""
        try:
            if not seasons:
                current_year = datetime.now().year
                seasons = [current_year - 2, current_year - 1, current_year]  # Last 3 seasons
            
            results = {
                "seasons_processed": [],
                "players_updated": 0,
                "performance_records_added": 0,
                "sleeper_ids_populated": 0,
                "errors": []
            }
            
            # First, ensure all players have Sleeper IDs
            logger.info("Populating Sleeper IDs for players...")
            sleeper_ids_result = await self._populate_sleeper_ids()
            results["sleeper_ids_populated"] = sleeper_ids_result.get("populated_count", 0)
            if sleeper_ids_result.get("errors"):
                results["errors"].extend(sleeper_ids_result["errors"])
            
            for season in seasons:
                try:
                    logger.info(f"Syncing historical data for season {season}")
                    season_result = await self._sync_season_data(season)
                    results["seasons_processed"].append(season)
                    results["players_updated"] += season_result.get("players_updated", 0)
                    results["performance_records_added"] += season_result.get("records_added", 0)
                except Exception as e:
                    error_msg = f"Error syncing season {season}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Generate season summaries after data sync
            await self._generate_season_summaries(seasons)
            
            # Analyze trends after summaries
            await self._analyze_player_trends(seasons)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in sync_historical_data: {str(e)}")
            return {"error": str(e)}

    async def sync_specific_player(self, player_id: int, seasons: List[int] = None) -> Dict[str, Any]:
        """Sync historical data for a specific player"""
        try:
            if not seasons:
                current_year = datetime.now().year
                seasons = [current_year - 2, current_year - 1, current_year]  # Last 3 seasons
            
            # Get the player
            player = self.db.query(Player).filter(Player.id == player_id).first()
            if not player:
                return {"error": f"Player with ID {player_id} not found"}
            
            if not player.sleeper_id:
                return {"error": f"Player {player.name} has no Sleeper ID"}
            
            results = {
                "player_name": player.name,
                "seasons_processed": [],
                "performance_records_added": 0,
                "errors": []
            }
            
            # Sync data for each season
            for season in seasons:
                try:
                    logger.info(f"Syncing season {season} data for player {player.name}")
                    season_result = await self._sync_player_season_data(player, season)
                    
                    results["seasons_processed"].append(season)
                    results["performance_records_added"] += season_result.get("records_added", 0)
                    
                    if season_result.get("errors"):
                        results["errors"].extend(season_result["errors"])
                        
                except Exception as e:
                    error_msg = f"Error syncing season {season} for player {player.name}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Generate season summaries for this player
            await self._generate_player_season_summaries(player, seasons)
            
            # Analyze trends for this player
            await self._analyze_single_player_trends(player, seasons)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in sync_specific_player: {str(e)}")
            return {"error": str(e)}

    async def _sync_player_season_data(self, player: Player, season: int) -> Dict[str, Any]:
        """Sync data for a specific player and season"""
        records_added = 0
        errors = []
        
        try:
            # Get historical stats from Sleeper
            stats = await sleeper_service.get_player_stats(player.sleeper_id, str(season))
            
            if stats and "error" not in stats:
                # Process weekly data
                weekly_data = await self._process_weekly_stats(player, season, stats)
                records_added += len(weekly_data)
                
                # Process season totals
                season_data = await self._process_season_stats(player, season, stats)
                if season_data:
                    records_added += 1
                    
            else:
                error_msg = f"No stats available for {player.name} in season {season}"
                logger.warning(error_msg)
                errors.append(error_msg)
                
        except Exception as e:
            error_msg = f"Error syncing {player.name} for season {season}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
        
        return {
            "records_added": records_added,
            "errors": errors
        }

    async def _generate_player_season_summaries(self, player: Player, seasons: List[int]):
        """Generate season summaries for a specific player"""
        try:
            for season in seasons:
                # Check if summary already exists
                existing = self.db.query(PlayerSeasonSummary).filter(
                    and_(
                        PlayerSeasonSummary.player_id == player.id,
                        PlayerSeasonSummary.season == season
                    )
                ).first()
                
                if not existing:
                    # Calculate summary from weekly data
                    summary = await self._calculate_season_summary(player, season)
                    if summary:
                        self.db.add(summary)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error generating season summaries for {player.name}: {str(e)}")
            self.db.rollback()

    async def _analyze_single_player_trends(self, player: Player, seasons: List[int]):
        """Analyze trends for a specific player"""
        try:
            # Analyze career trend
            await self._analyze_career_trend(player)
            
            # Analyze season-over-season trends
            for season in seasons:
                await self._analyze_season_trend(player, season)
                
        except Exception as e:
            logger.error(f"Error analyzing trends for {player.name}: {str(e)}")

    async def _sync_season_data(self, season: int) -> Dict[str, Any]:
        """Sync data for a specific season"""
        players_updated = 0
        records_added = 0
        
        # Get all players to sync
        players = self.db.query(Player).all()
        
        for player in players:
            if player.sleeper_id:
                try:
                    # Get historical stats from Sleeper
                    stats = await sleeper_service.get_player_stats(player.sleeper_id, str(season))
                    
                    if stats and "error" not in stats:
                        # Process weekly data
                        weekly_data = await self._process_weekly_stats(player, season, stats)
                        records_added += len(weekly_data)
                        
                        # Process season totals
                        season_data = await self._process_season_stats(player, season, stats)
                        if season_data:
                            records_added += 1
                        
                        players_updated += 1
                        
                except Exception as e:
                    logger.error(f"Error syncing player {player.name}: {str(e)}")
                    continue
        
        return {
            "players_updated": players_updated,
            "records_added": records_added
        }

    async def _process_weekly_stats(self, player: Player, season: int, stats: Dict) -> List[PlayerHistoricalPerformance]:
        """Process weekly statistics into historical performance records"""
        weekly_records = []
        
        # Extract weekly stats from API response
        weekly_stats = stats.get("weekly", {})
        
        for week_str, week_data in weekly_stats.items():
            try:
                week = int(week_str)
                
                # Check if record already exists
                existing = self.db.query(PlayerHistoricalPerformance).filter(
                    and_(
                        PlayerHistoricalPerformance.player_id == player.id,
                        PlayerHistoricalPerformance.season == season,
                        PlayerHistoricalPerformance.week == week
                    )
                ).first()
                
                if existing:
                    continue  # Skip if already exists
                
                # Calculate fantasy points from stats
                fantasy_points = self._calculate_fantasy_points(week_data, player.position.value)
                
                # Create performance record
                performance = PlayerHistoricalPerformance(
                    player_id=player.id,
                    season=season,
                    week=week,
                    performance_type=PerformanceType.WEEKLY.value,
                    
                    # Fantasy scoring
                    fantasy_points_ppr=fantasy_points.get("ppr", 0),
                    fantasy_points_half_ppr=fantasy_points.get("half_ppr", 0),
                    fantasy_points_standard=fantasy_points.get("standard", 0),
                    
                    # Position-specific stats
                    passing_stats=self._extract_passing_stats(week_data),
                    rushing_stats=self._extract_rushing_stats(week_data),
                    receiving_stats=self._extract_receiving_stats(week_data),
                    defensive_stats=self._extract_defensive_stats(week_data),
                    kicking_stats=self._extract_kicking_stats(week_data),
                    
                    # Advanced metrics
                    snap_count=week_data.get("snaps"),
                    snap_percentage=week_data.get("snap_percentage"),
                    target_share=week_data.get("target_share"),
                    
                    data_source="sleeper"
                )
                
                self.db.add(performance)
                weekly_records.append(performance)
                
            except Exception as e:
                logger.error(f"Error processing week {week_str} for {player.name}: {str(e)}")
                continue
        
        self.db.commit()
        return weekly_records

    async def _process_season_stats(self, player: Player, season: int, stats: Dict) -> Optional[PlayerSeasonSummary]:
        """Process season totals into summary record"""
        try:
            # Check if summary already exists
            existing = self.db.query(PlayerSeasonSummary).filter(
                and_(
                    PlayerSeasonSummary.player_id == player.id,
                    PlayerSeasonSummary.season == season
                )
            ).first()
            
            if existing:
                return None  # Skip if already exists
            
            # Get all weekly performances for this player/season
            weekly_performances = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player.id,
                    PlayerHistoricalPerformance.season == season,
                    PlayerHistoricalPerformance.week.isnot(None)
                )
            ).all()
            
            if not weekly_performances:
                return None
            
            # Calculate season metrics
            games_played = len(weekly_performances)
            fantasy_points = [p.fantasy_points_ppr for p in weekly_performances if p.fantasy_points_ppr]
            
            if not fantasy_points:
                return None
            
            total_points = sum(fantasy_points)
            avg_points = total_points / games_played
            
            # Calculate consistency metrics
            ceiling = max(fantasy_points)
            floor = min(fantasy_points)
            std_dev = statistics.stdev(fantasy_points) if len(fantasy_points) > 1 else 0
            consistency_score = 1 - (std_dev / avg_points) if avg_points > 0 else 0
            
            # Calculate boom/bust weeks
            boom_threshold = avg_points * 1.5
            bust_threshold = avg_points * 0.5
            boom_weeks = len([fp for fp in fantasy_points if fp >= boom_threshold])
            bust_weeks = len([fp for fp in fantasy_points if fp <= bust_threshold])
            
            # Calculate half-season splits
            mid_point = len(fantasy_points) // 2
            first_half_avg = sum(fantasy_points[:mid_point]) / mid_point if mid_point > 0 else 0
            second_half_avg = sum(fantasy_points[mid_point:]) / (len(fantasy_points) - mid_point) if mid_point < len(fantasy_points) else 0
            
            # Determine trend
            trend_direction = "stable"
            if second_half_avg > first_half_avg * 1.1:
                trend_direction = "improving"
            elif second_half_avg < first_half_avg * 0.9:
                trend_direction = "declining"
            
            # Create season summary
            summary = PlayerSeasonSummary(
                player_id=player.id,
                season=season,
                games_played=games_played,
                
                # Fantasy totals
                total_fantasy_points_ppr=total_points,
                avg_fantasy_points_ppr=avg_points,
                
                # Consistency metrics
                weekly_ceiling=ceiling,
                weekly_floor=floor,
                consistency_score=consistency_score,
                boom_weeks=boom_weeks,
                bust_weeks=bust_weeks,
                
                # Trend analysis
                first_half_avg=first_half_avg,
                second_half_avg=second_half_avg,
                trend_direction=trend_direction
            )
            
            self.db.add(summary)
            self.db.commit()
            
            return summary
            
        except Exception as e:
            logger.error(f"Error processing season summary for {player.name}: {str(e)}")
            return None

    async def _generate_season_summaries(self, seasons: List[int]):
        """Generate comprehensive season summaries for all players"""
        logger.info("Generating season summaries...")
        
        for season in seasons:
            players_with_data = self.db.query(Player).join(PlayerHistoricalPerformance).filter(
                PlayerHistoricalPerformance.season == season
            ).distinct().all()
            
            for player in players_with_data:
                await self._process_season_stats(player, season, {})

    async def _analyze_player_trends(self, seasons: List[int]):
        """Analyze player performance trends across multiple timeframes"""
        logger.info("Analyzing player trends...")
        
        players = self.db.query(Player).all()
        
        for player in players:
            try:
                # Analyze career trend
                await self._analyze_career_trend(player)
                
                # Analyze season-over-season trends
                for season in seasons:
                    await self._analyze_season_trend(player, season)
                    
            except Exception as e:
                logger.error(f"Error analyzing trends for {player.name}: {str(e)}")

    async def _analyze_career_trend(self, player: Player):
        """Analyze player's career performance trend"""
        try:
            # Get all season summaries
            summaries = self.db.query(PlayerSeasonSummary).filter(
                PlayerSeasonSummary.player_id == player.id
            ).order_by(PlayerSeasonSummary.season).all()
            
            if len(summaries) < 2:
                return  # Need at least 2 seasons
            
            # Calculate trend metrics
            seasons = [s.season for s in summaries]
            avg_points = [s.avg_fantasy_points_ppr for s in summaries if s.avg_fantasy_points_ppr]
            
            if len(avg_points) < 2:
                return
            
            # Calculate slope (trend direction)
            x = list(range(len(avg_points)))
            slope = np.polyfit(x, avg_points, 1)[0]
            
            # Determine trend characteristics
            trend_direction = "stable"
            trend_strength = abs(slope) / (sum(avg_points) / len(avg_points))  # Normalized slope
            
            if slope > 0.5:
                trend_direction = "up"
            elif slope < -0.5:
                trend_direction = "down"
            
            # Calculate performance change
            performance_change = ((avg_points[-1] - avg_points[0]) / avg_points[0] * 100) if avg_points[0] > 0 else 0
            
            # Check for existing career trend
            existing_trend = self.db.query(PlayerTrend).filter(
                and_(
                    PlayerTrend.player_id == player.id,
                    PlayerTrend.trend_type == "career"
                )
            ).first()
            
            if existing_trend:
                # Update existing trend
                existing_trend.trend_direction = trend_direction
                existing_trend.trend_strength = trend_strength
                existing_trend.performance_change = performance_change
                existing_trend.last_updated = datetime.utcnow()
            else:
                # Create new trend
                trend = PlayerTrend(
                    player_id=player.id,
                    trend_start_date=datetime(summaries[0].season, 9, 1),
                    trend_end_date=datetime(summaries[-1].season, 12, 31),
                    trend_type="career",
                    trend_direction=trend_direction,
                    trend_strength=trend_strength,
                    performance_change=performance_change,
                    sample_size=len(summaries)
                )
                self.db.add(trend)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error analyzing career trend for {player.name}: {str(e)}")

    async def _analyze_season_trend(self, player: Player, season: int):
        """Analyze player's within-season trend"""
        try:
            # Get weekly performances for the season
            performances = self.db.query(PlayerHistoricalPerformance).filter(
                and_(
                    PlayerHistoricalPerformance.player_id == player.id,
                    PlayerHistoricalPerformance.season == season,
                    PlayerHistoricalPerformance.week.isnot(None)
                )
            ).order_by(PlayerHistoricalPerformance.week).all()
            
            if len(performances) < 8:  # Need at least 8 games
                return
            
            fantasy_points = [p.fantasy_points_ppr for p in performances if p.fantasy_points_ppr]
            
            if len(fantasy_points) < 8:
                return
            
            # Analyze recent 8-week trend
            recent_points = fantasy_points[-8:]
            x = list(range(len(recent_points)))
            slope = np.polyfit(x, recent_points, 1)[0]
            
            # Determine trend characteristics
            trend_direction = "stable"
            if slope > 0.3:
                trend_direction = "up"
            elif slope < -0.3:
                trend_direction = "down"
            
            trend_strength = abs(slope) / (sum(recent_points) / len(recent_points))
            performance_change = ((recent_points[-1] - recent_points[0]) / recent_points[0] * 100) if recent_points[0] > 0 else 0
            
            # Check for existing season trend
            existing_trend = self.db.query(PlayerTrend).filter(
                and_(
                    PlayerTrend.player_id == player.id,
                    PlayerTrend.trend_type == "8_week",
                    func.extract('year', PlayerTrend.trend_end_date) == season
                )
            ).first()
            
            if existing_trend:
                # Update existing trend
                existing_trend.trend_direction = trend_direction
                existing_trend.trend_strength = trend_strength
                existing_trend.performance_change = performance_change
                existing_trend.last_updated = datetime.utcnow()
            else:
                # Create new trend
                trend = PlayerTrend(
                    player_id=player.id,
                    trend_start_date=datetime(season, 9, 1),
                    trend_end_date=datetime(season, 12, 31),
                    trend_type="8_week",
                    trend_direction=trend_direction,
                    trend_strength=trend_strength,
                    performance_change=performance_change,
                    sample_size=len(recent_points)
                )
                self.db.add(trend)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error analyzing season trend for {player.name}: {str(e)}")

    def _calculate_fantasy_points(self, stats: Dict, position: str) -> Dict[str, float]:
        """Calculate fantasy points from raw stats"""
        points = {"ppr": 0, "half_ppr": 0, "standard": 0}
        
        try:
            # Passing stats
            pass_yds = stats.get("pass_yds", 0) or 0
            pass_td = stats.get("pass_td", 0) or 0
            pass_int = stats.get("pass_int", 0) or 0
            
            # Rushing stats
            rush_yds = stats.get("rush_yds", 0) or 0
            rush_td = stats.get("rush_td", 0) or 0
            
            # Receiving stats
            rec_yds = stats.get("rec_yds", 0) or 0
            rec_td = stats.get("rec_td", 0) or 0
            rec = stats.get("rec", 0) or 0
            
            # Fumbles
            fumbles_lost = stats.get("fum_lost", 0) or 0
            
            # Calculate base points (standard scoring)
            base_points = (
                (pass_yds * 0.04) +  # 1 point per 25 passing yards
                (pass_td * 4) +      # 4 points per passing TD
                (pass_int * -2) +    # -2 points per interception
                (rush_yds * 0.1) +   # 1 point per 10 rushing yards
                (rush_td * 6) +      # 6 points per rushing TD
                (rec_yds * 0.1) +    # 1 point per 10 receiving yards
                (rec_td * 6) +       # 6 points per receiving TD
                (fumbles_lost * -2)  # -2 points per fumble lost
            )
            
            points["standard"] = base_points
            points["half_ppr"] = base_points + (rec * 0.5)  # +0.5 per reception
            points["ppr"] = base_points + rec  # +1 per reception
            
            # Handle kickers and defense separately
            if position == "K":
                points = self._calculate_kicker_points(stats)
            elif position == "DEF":
                points = self._calculate_defense_points(stats)
            
        except Exception as e:
            logger.error(f"Error calculating fantasy points: {str(e)}")
        
        return points

    def _calculate_kicker_points(self, stats: Dict) -> Dict[str, float]:
        """Calculate kicker fantasy points"""
        points = {"ppr": 0, "half_ppr": 0, "standard": 0}
        
        try:
            xp_made = stats.get("xp_made", 0) or 0
            fg_made = stats.get("fg_made", 0) or 0
            fg_missed = stats.get("fg_missed", 0) or 0
            
            # Basic scoring (simplified)
            total_points = (xp_made * 1) + (fg_made * 3) + (fg_missed * -1)
            
            points["standard"] = total_points
            points["half_ppr"] = total_points
            points["ppr"] = total_points
            
        except Exception as e:
            logger.error(f"Error calculating kicker points: {str(e)}")
        
        return points

    def _calculate_defense_points(self, stats: Dict) -> Dict[str, float]:
        """Calculate defense fantasy points"""
        points = {"ppr": 0, "half_ppr": 0, "standard": 0}
        
        try:
            sacks = stats.get("sacks", 0) or 0
            ints = stats.get("def_int", 0) or 0
            fumbles_rec = stats.get("def_fumbles_rec", 0) or 0
            def_td = stats.get("def_td", 0) or 0
            
            # Simplified defense scoring
            total_points = (sacks * 1) + (ints * 2) + (fumbles_rec * 2) + (def_td * 6)
            
            points["standard"] = total_points
            points["half_ppr"] = total_points
            points["ppr"] = total_points
            
        except Exception as e:
            logger.error(f"Error calculating defense points: {str(e)}")
        
        return points

    async def _populate_sleeper_ids(self) -> Dict[str, Any]:
        """Populate Sleeper IDs for players that don't have them"""
        try:
            # Get all players without Sleeper IDs
            players_without_ids = self.db.query(Player).filter(
                or_(Player.sleeper_id.is_(None), Player.sleeper_id == "")
            ).all()
            
            if not players_without_ids:
                return {"populated_count": 0, "message": "All players already have Sleeper IDs"}
            
            # Get all Sleeper players
            sleeper_players = await sleeper_service.get_all_players()
            
            if "error" in sleeper_players:
                return {"populated_count": 0, "errors": [sleeper_players["error"]]}
            
            populated_count = 0
            errors = []
            
            # Match players by name and position
            for player in players_without_ids:
                try:
                    # Find matching Sleeper player
                    sleeper_id = self._find_sleeper_match(player, sleeper_players)
                    
                    if sleeper_id:
                        player.sleeper_id = sleeper_id
                        populated_count += 1
                        logger.info(f"Populated Sleeper ID {sleeper_id} for {player.name}")
                    else:
                        logger.warning(f"No Sleeper match found for {player.name}")
                        
                except Exception as e:
                    error_msg = f"Error matching {player.name}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            self.db.commit()
            
            return {
                "populated_count": populated_count,
                "total_processed": len(players_without_ids),
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Error populating Sleeper IDs: {str(e)}")
            return {"populated_count": 0, "errors": [str(e)]}
    
    def _find_sleeper_match(self, player: Player, sleeper_players: Dict) -> Optional[str]:
        """Find matching Sleeper player ID for a given player"""
        try:
            player_name_lower = player.name.lower()
            player_pos = player.position.value if hasattr(player.position, 'value') else str(player.position)
            
            # Exact name match with position
            for sleeper_id, sleeper_data in sleeper_players.items():
                if not isinstance(sleeper_data, dict):
                    continue
                    
                sleeper_name = sleeper_data.get("full_name", "").lower()
                sleeper_pos = sleeper_data.get("position", "")
                
                # Exact match
                if sleeper_name == player_name_lower and sleeper_pos == player_pos:
                    return sleeper_id
            
            # Fuzzy name matching for common variations
            name_variations = self._generate_name_variations(player.name)
            
            for sleeper_id, sleeper_data in sleeper_players.items():
                if not isinstance(sleeper_data, dict):
                    continue
                    
                sleeper_name = sleeper_data.get("full_name", "").lower()
                sleeper_pos = sleeper_data.get("position", "")
                
                if sleeper_pos == player_pos:
                    for variation in name_variations:
                        if variation.lower() == sleeper_name:
                            return sleeper_id
                            
                    # Also check first_name + last_name combination
                    first_name = sleeper_data.get("first_name", "").lower()
                    last_name = sleeper_data.get("last_name", "").lower()
                    full_from_parts = f"{first_name} {last_name}".strip()
                    
                    if full_from_parts == player_name_lower:
                        return sleeper_id
                        
            return None
            
        except Exception as e:
            logger.error(f"Error in Sleeper match for {player.name}: {str(e)}")
            return None
    
    def _generate_name_variations(self, name: str) -> List[str]:
        """Generate common name variations for matching"""
        variations = [name]
        
        # Handle common nickname patterns
        parts = name.split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            
            # Common nicknames
            nickname_map = {
                "Christopher": "Chris", "Michael": "Mike", "William": "Will", "Robert": "Rob",
                "Richard": "Rick", "Anthony": "Tony", "Alexander": "Alex", "Benjamin": "Ben",
                "Matthew": "Matt", "Daniel": "Dan", "Jonathan": "Jon", "Nicholas": "Nick",
                "Kenneth": "Ken", "Joseph": "Joe", "Timothy": "Tim", "Joshua": "Josh",
                "Andrew": "Andy", "Charles": "Chuck", "Thomas": "Tom", "David": "Dave"
            }
            
            # Check if first name has common nickname
            for full, nick in nickname_map.items():
                if first == full:
                    variations.append(f"{nick} {last}")
                elif first == nick:
                    variations.append(f"{full} {last}")
        
        return variations

    def _extract_passing_stats(self, stats: Dict) -> Optional[Dict]:
        """Extract passing statistics"""
        if not any(key.startswith("pass_") for key in stats.keys()):
            return None
        
        return {
            "yards": stats.get("pass_yds", 0),
            "touchdowns": stats.get("pass_td", 0),
            "interceptions": stats.get("pass_int", 0),
            "completions": stats.get("pass_cmp", 0),
            "attempts": stats.get("pass_att", 0),
            "completion_percentage": stats.get("pass_cmp_percentage"),
            "yards_per_attempt": stats.get("pass_ypa")
        }

    def _extract_rushing_stats(self, stats: Dict) -> Optional[Dict]:
        """Extract rushing statistics"""
        if not any(key.startswith("rush_") for key in stats.keys()):
            return None
        
        return {
            "yards": stats.get("rush_yds", 0),
            "touchdowns": stats.get("rush_td", 0),
            "attempts": stats.get("rush_att", 0),
            "fumbles": stats.get("fum", 0),
            "yards_per_attempt": stats.get("rush_ypa"),
            "long": stats.get("rush_lng")
        }

    def _extract_receiving_stats(self, stats: Dict) -> Optional[Dict]:
        """Extract receiving statistics"""
        if not any(key.startswith("rec_") for key in stats.keys()):
            return None
        
        return {
            "yards": stats.get("rec_yds", 0),
            "touchdowns": stats.get("rec_td", 0),
            "receptions": stats.get("rec", 0),
            "targets": stats.get("rec_tgt", 0),
            "yards_per_reception": stats.get("rec_ypr"),
            "yards_after_catch": stats.get("rec_yac"),
            "long": stats.get("rec_lng")
        }

    def _extract_defensive_stats(self, stats: Dict) -> Optional[Dict]:
        """Extract defensive statistics"""
        def_keys = ["sacks", "def_int", "def_fumbles_rec", "def_td", "tackles"]
        if not any(key in stats for key in def_keys):
            return None
        
        return {
            "sacks": stats.get("sacks", 0),
            "interceptions": stats.get("def_int", 0),
            "fumbles_recovered": stats.get("def_fumbles_rec", 0),
            "touchdowns": stats.get("def_td", 0),
            "tackles": stats.get("tackles", 0)
        }

    def _extract_kicking_stats(self, stats: Dict) -> Optional[Dict]:
        """Extract kicking statistics"""
        if not any(key.startswith(("fg_", "xp_")) for key in stats.keys()):
            return None
        
        return {
            "field_goals_made": stats.get("fg_made", 0),
            "field_goals_attempted": stats.get("fg_att", 0),
            "extra_points_made": stats.get("xp_made", 0),
            "extra_points_attempted": stats.get("xp_att", 0),
            "field_goal_percentage": stats.get("fg_percentage")
        }

    async def get_player_historical_summary(self, player_id: int, seasons: int = 3) -> Dict[str, Any]:
        """Get comprehensive historical summary for a player"""
        try:
            # First just check if player exists using basic query
            player_exists = self.db.query(Player.id, Player.name, Player.position).filter(Player.id == player_id).first()
            if not player_exists:
                return {"error": "Player not found"}
            
            current_year = datetime.now().year
            season_range = list(range(current_year - seasons + 1, current_year + 1))
            
            # Get season summaries (these don't have enum issues)
            summaries = self.db.query(PlayerSeasonSummary).filter(
                and_(
                    PlayerSeasonSummary.player_id == player_id,
                    PlayerSeasonSummary.season.in_(season_range)
                )
            ).order_by(PlayerSeasonSummary.season.desc()).all()
            
            # If no season summaries exist, calculate from weekly data using raw SQL to avoid enum issues
            if not summaries:
                # Use raw SQL to get historical performance data
                from sqlalchemy import text
                sql = text("""
                    SELECT season, week, fantasy_points_ppr, fantasy_points_half_ppr, fantasy_points_standard
                    FROM player_historical_performance 
                    WHERE player_id = :player_id 
                    AND season IN :season_range 
                    AND week IS NOT NULL
                    ORDER BY season, week
                """)
                
                weekly_result = self.db.execute(sql, {
                    "player_id": player_id, 
                    "season_range": tuple(season_range)
                }).fetchall()
                
                if weekly_result:
                    # Group by season and calculate summaries
                    season_data = {}
                    for row in weekly_result:
                        season, week, ppr, half_ppr, standard = row
                        if season not in season_data:
                            season_data[season] = []
                        season_data[season].append({
                            'week': week,
                            'ppr': ppr,
                            'half_ppr': half_ppr,
                            'standard': standard
                        })
                    
                    calculated_summaries = []
                    for season, performances in season_data.items():
                        fantasy_points = [p['ppr'] for p in performances if p['ppr'] is not None]
                        if fantasy_points:
                            games_played = len(fantasy_points)
                            total_points = sum(fantasy_points)
                            avg_points = total_points / games_played
                            ceiling = max(fantasy_points)
                            floor = min(fantasy_points)
                            
                            # Simple consistency calculation
                            if len(fantasy_points) > 1:
                                import statistics
                                std_dev = statistics.stdev(fantasy_points)
                                consistency_score = 1 - (std_dev / avg_points) if avg_points > 0 else 0
                                consistency_score = max(0, min(1, consistency_score))  # Clamp between 0 and 1
                            else:
                                consistency_score = 1.0
                            
                            calculated_summaries.append({
                                "season": season,
                                "games_played": games_played,
                                "avg_points": avg_points,
                                "total_points": total_points,
                                "consistency_score": consistency_score,
                                "ceiling": ceiling,
                                "floor": floor,
                                "boom_weeks": len([fp for fp in fantasy_points if fp >= avg_points * 1.5]),
                                "bust_weeks": len([fp for fp in fantasy_points if fp <= avg_points * 0.5]),
                                "trend_direction": "stable",
                                "position_finish": None
                            })
                    
                    summaries = calculated_summaries
                else:
                    summaries = []
            else:
                # Convert SQLAlchemy objects to dicts for consistent processing
                summaries = [
                    {
                        "season": s.season,
                        "games_played": s.games_played,
                        "avg_points": s.avg_fantasy_points_ppr,
                        "total_points": s.total_fantasy_points_ppr,
                        "consistency_score": s.consistency_score,
                        "ceiling": s.weekly_ceiling,
                        "floor": s.weekly_floor,
                        "boom_weeks": s.boom_weeks,
                        "bust_weeks": s.bust_weeks,
                        "trend_direction": s.trend_direction,
                        "position_finish": s.position_finish
                    }
                    for s in summaries
                ]
            
            # Calculate historical metrics
            if summaries:
                avg_points_history = [s["avg_points"] for s in summaries if s["avg_points"]]
                consistency_history = [s["consistency_score"] for s in summaries if s["consistency_score"]]
                
                historical_avg = sum(avg_points_history) / len(avg_points_history) if avg_points_history else 0
                historical_consistency = sum(consistency_history) / len(consistency_history) if consistency_history else 0
            else:
                historical_avg = 0
                historical_consistency = 0
            
            return {
                "player_id": player_id,
                "player_name": player_exists.name,
                "position": player_exists.position.value if hasattr(player_exists.position, 'value') else str(player_exists.position),
                "seasons_analyzed": len(summaries),
                "historical_average": historical_avg,
                "historical_consistency": historical_consistency,
                "season_summaries": summaries,
                "career_trend": None,  # Skip trends for now due to enum issues
                "recent_trend": None,  # Skip trends for now due to enum issues
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # If no season summaries exist, calculate from weekly data on the fly
            if not summaries:
                weekly_performances = self.db.query(PlayerHistoricalPerformance).filter(
                    and_(
                        PlayerHistoricalPerformance.player_id == player_id,
                        PlayerHistoricalPerformance.season.in_(season_range),
                        PlayerHistoricalPerformance.week.isnot(None)
                    )
                ).order_by(PlayerHistoricalPerformance.season, PlayerHistoricalPerformance.week).all()
                
                if weekly_performances:
                    # Group by season and calculate summaries
                    season_data = {}
                    for perf in weekly_performances:
                        if perf.season not in season_data:
                            season_data[perf.season] = []
                        season_data[perf.season].append(perf)
                    
                    calculated_summaries = []
                    for season, performances in season_data.items():
                        fantasy_points = [p.fantasy_points_ppr for p in performances if p.fantasy_points_ppr is not None]
                        if fantasy_points:
                            games_played = len(fantasy_points)
                            total_points = sum(fantasy_points)
                            avg_points = total_points / games_played
                            ceiling = max(fantasy_points)
                            floor = min(fantasy_points)
                            
                            # Simple consistency calculation
                            if len(fantasy_points) > 1:
                                import statistics
                                std_dev = statistics.stdev(fantasy_points)
                                consistency_score = 1 - (std_dev / avg_points) if avg_points > 0 else 0
                                consistency_score = max(0, min(1, consistency_score))  # Clamp between 0 and 1
                            else:
                                consistency_score = 1.0
                            
                            calculated_summaries.append({
                                "season": season,
                                "games_played": games_played,
                                "avg_points": avg_points,
                                "total_points": total_points,
                                "consistency_score": consistency_score,
                                "ceiling": ceiling,
                                "floor": floor,
                                "boom_weeks": len([fp for fp in fantasy_points if fp >= avg_points * 1.5]),
                                "bust_weeks": len([fp for fp in fantasy_points if fp <= avg_points * 0.5]),
                                "trend_direction": "stable",
                                "position_finish": None
                            })
                    
                    summaries = calculated_summaries
            else:
                # Convert SQLAlchemy objects to dicts for consistent processing
                summaries = [
                    {
                        "season": s.season,
                        "games_played": s.games_played,
                        "avg_points": s.avg_fantasy_points_ppr,
                        "total_points": s.total_fantasy_points_ppr,
                        "consistency_score": s.consistency_score,
                        "ceiling": s.weekly_ceiling,
                        "floor": s.weekly_floor,
                        "boom_weeks": s.boom_weeks,
                        "bust_weeks": s.bust_weeks,
                        "trend_direction": s.trend_direction,
                        "position_finish": s.position_finish
                    }
                    for s in summaries
                ]
            
            # Get career trends
            career_trend = self.db.query(PlayerTrend).filter(
                and_(
                    PlayerTrend.player_id == player_id,
                    PlayerTrend.trend_type == "career"
                )
            ).first()
            
            # Get recent trend
            recent_trend = self.db.query(PlayerTrend).filter(
                and_(
                    PlayerTrend.player_id == player_id,
                    PlayerTrend.trend_type == "8_week"
                )
            ).order_by(PlayerTrend.last_updated.desc()).first()
            
            # Calculate historical metrics
            if summaries:
                avg_points_history = [s["avg_points"] for s in summaries if s["avg_points"]]
                consistency_history = [s["consistency_score"] for s in summaries if s["consistency_score"]]
                
                historical_avg = sum(avg_points_history) / len(avg_points_history) if avg_points_history else 0
                historical_consistency = sum(consistency_history) / len(consistency_history) if consistency_history else 0
            else:
                historical_avg = 0
                historical_consistency = 0
            
            return {
                "player_id": player_id,
                "player_name": player.name,
                "position": player.position.value if hasattr(player.position, 'value') else str(player.position),
                "seasons_analyzed": len(summaries),
                "historical_average": historical_avg,
                "historical_consistency": historical_consistency,
                "season_summaries": summaries,
                "career_trend": {
                    "direction": career_trend.trend_direction if career_trend else "unknown",
                    "strength": career_trend.trend_strength if career_trend else 0,
                    "performance_change": career_trend.performance_change if career_trend else 0
                } if career_trend else None,
                "recent_trend": {
                    "direction": recent_trend.trend_direction if recent_trend else "unknown",
                    "strength": recent_trend.trend_strength if recent_trend else 0,
                    "performance_change": recent_trend.performance_change if recent_trend else 0
                } if recent_trend else None,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting historical summary for player {player_id}: {str(e)}")
            return {"error": str(e)}

    async def get_position_historical_analysis(self, position: str, seasons: int = 3) -> Dict[str, Any]:
        """Get historical analysis for all players at a position"""
        try:
            current_year = datetime.now().year
            season_range = list(range(current_year - seasons + 1, current_year + 1))
            
            # Get all players at position with historical data
            players_with_data = self.db.query(Player).join(PlayerSeasonSummary).filter(
                and_(
                    Player.position == position,
                    PlayerSeasonSummary.season.in_(season_range)
                )
            ).distinct().all()
            
            position_analysis = {
                "position": position,
                "seasons_analyzed": seasons,
                "total_players": len(players_with_data),
                "players": []
            }
            
            for player in players_with_data:
                player_summary = await self.get_player_historical_summary(player.id, seasons)
                if "error" not in player_summary:
                    position_analysis["players"].append(player_summary)
            
            # Calculate position benchmarks
            if position_analysis["players"]:
                all_avgs = [p["historical_average"] for p in position_analysis["players"] if p["historical_average"] > 0]
                all_consistency = [p["historical_consistency"] for p in position_analysis["players"] if p["historical_consistency"] > 0]
                
                position_analysis["benchmarks"] = {
                    "average_points": sum(all_avgs) / len(all_avgs) if all_avgs else 0,
                    "average_consistency": sum(all_consistency) / len(all_consistency) if all_consistency else 0,
                    "top_performer_threshold": np.percentile(all_avgs, 80) if len(all_avgs) >= 5 else 0,
                    "bust_threshold": np.percentile(all_avgs, 20) if len(all_avgs) >= 5 else 0
                }
            
            return position_analysis
            
        except Exception as e:
            logger.error(f"Error getting position analysis for {position}: {str(e)}")
            return {"error": str(e)}

    async def compare_players_historically(self, player_ids: List[int], seasons: int = 3) -> Dict[str, Any]:
        """Compare multiple players' historical performance"""
        try:
            comparison = {
                "players": [],
                "comparison_metrics": {},
                "seasons_analyzed": seasons
            }
            
            for player_id in player_ids:
                player_summary = await self.get_player_historical_summary(player_id, seasons)
                if "error" not in player_summary:
                    comparison["players"].append(player_summary)
            
            if len(comparison["players"]) >= 2:
                # Calculate comparison metrics
                comparison["comparison_metrics"] = self._calculate_comparison_metrics(comparison["players"])
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error comparing players: {str(e)}")
            return {"error": str(e)}

    def _calculate_comparison_metrics(self, players: List[Dict]) -> Dict[str, Any]:
        """Calculate comparison metrics between players"""
        metrics = {}
        
        try:
            # Compare historical averages
            averages = [p["historical_average"] for p in players if p["historical_average"] > 0]
            if averages:
                metrics["highest_average"] = max(averages)
                metrics["lowest_average"] = min(averages)
                metrics["average_spread"] = max(averages) - min(averages)
            
            # Compare consistency
            consistency_scores = [p["historical_consistency"] for p in players if p["historical_consistency"] > 0]
            if consistency_scores:
                metrics["most_consistent"] = max(consistency_scores)
                metrics["least_consistent"] = min(consistency_scores)
            
            # Compare trends
            trend_directions = [p.get("career_trend", {}).get("direction", "unknown") for p in players]
            metrics["trending_up"] = trend_directions.count("up")
            metrics["trending_down"] = trend_directions.count("down")
            metrics["stable"] = trend_directions.count("stable")
            
        except Exception as e:
            logger.error(f"Error calculating comparison metrics: {str(e)}")
        
        return metrics