from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from app.models.player import Player
from app.models.game_situation import (
    GameSituation, DefensiveRanking, VenueData, WeatherHistory, SituationalTrend,
    WEATHER_CONDITIONS, GAME_SCRIPTS, VENUE_TYPES
)
from app.models.historical_performance import PlayerHistoricalPerformance
from app.models.nfl_schedule import NFLGame
from app.services.matchup_analysis_service import MatchupAnalysisService
from datetime import datetime, timedelta
import statistics
import numpy as np
from collections import defaultdict
import asyncio
import json

class EnhancedGameSituationService:
    """
    Advanced game situation analysis with real NFL data integration
    """
    
    def __init__(self, db: Session):
        self.db = db
        
    async def analyze_comprehensive_game_situations(self, player_ids: List[int], 
                                                  analysis_type: str = "all") -> Dict[str, Any]:
        """
        Comprehensive game situation analysis with real data
        """
        try:
            players = self.db.query(Player).filter(Player.id.in_(player_ids)).all()
            if not players:
                return {"error": "No players found"}
            
            analysis_results = []
            
            for player in players:
                player_analysis = {
                    'player': {
                        'id': player.id,
                        'name': player.name,
                        'position': player.position.value if player.position else 'Unknown',
                        'team': player.team
                    }
                }
                
                # Perform different types of analysis based on request
                if analysis_type in ["all", "home_away"]:
                    player_analysis['home_away_analysis'] = await self._enhanced_home_away_analysis(player.id)
                
                if analysis_type in ["all", "weather"]:
                    player_analysis['weather_analysis'] = await self._enhanced_weather_analysis(player.id)
                
                if analysis_type in ["all", "opponent"]:
                    player_analysis['opponent_analysis'] = await self._enhanced_opponent_analysis(player.id)
                
                if analysis_type in ["all", "game_script"]:
                    player_analysis['game_script_analysis'] = await self._enhanced_game_script_analysis(player.id)
                
                if analysis_type in ["all", "venue"]:
                    player_analysis['venue_analysis'] = await self._enhanced_venue_analysis(player.id)
                
                if analysis_type in ["all", "prime_time"]:
                    player_analysis['prime_time_analysis'] = await self._prime_time_analysis(player.id)
                
                if analysis_type in ["all", "rivalry"]:
                    player_analysis['rivalry_analysis'] = await self._rivalry_game_analysis(player.id)
                
                # Generate comprehensive insights
                player_analysis['situational_insights'] = await self._generate_comprehensive_insights(player.id)
                player_analysis['upcoming_situation_forecast'] = await self._forecast_upcoming_situations(player)
                
                analysis_results.append(player_analysis)
            
            # Cross-player comparison insights
            comparison_insights = await self._generate_cross_situational_insights(analysis_results)
            
            return {
                "success": True,
                "analysis_type": analysis_type,
                "player_analyses": analysis_results,
                "comparison_insights": comparison_insights,
                "recommendations": await self._generate_situational_recommendations(analysis_results)
            }
            
        except Exception as e:
            return {"error": f"Enhanced game situation analysis failed: {str(e)}"}
    
    async def _enhanced_home_away_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Enhanced home vs away analysis with venue-specific data
        """
        # Get game situations for home/away splits
        home_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_home_game == True)
        ).all()
        
        away_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_home_game == False)
        ).all()
        
        # Calculate detailed statistics
        home_stats = self._calculate_situational_stats(home_games)
        away_stats = self._calculate_situational_stats(away_games)
        
        # Venue-specific analysis
        venue_performance = defaultdict(list)
        for game in away_games:
            if game.venue_name:
                venue_performance[game.venue_name].append(game.fantasy_points)
        
        venue_analysis = {}
        for venue, points in venue_performance.items():
            if len(points) >= 2:  # Minimum sample size
                venue_analysis[venue] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points),
                    'consistency': round(1 - (statistics.stdev(points) / statistics.mean(points)), 3) if statistics.mean(points) > 0 else 0
                }
        
        # Travel distance impact: honestly reports insufficient data rather
        # than a real calculation -- see _analyze_travel_impact's docstring.
        travel_impact = await self._analyze_travel_impact(player_id, away_games)
        
        return {
            'home_performance': home_stats,
            'away_performance': away_stats,
            'advantage': 'HOME' if home_stats['avg_points'] > away_stats['avg_points'] else 'AWAY',
            'home_away_differential': round(home_stats['avg_points'] - away_stats['avg_points'], 2),
            'venue_specific_performance': venue_analysis,
            'travel_impact': travel_impact,
            'confidence': self._calculate_confidence(len(home_games) + len(away_games)),
            'recommendations': self._generate_home_away_recommendations(home_stats, away_stats, venue_analysis)
        }
    
    async def _enhanced_weather_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Advanced weather impact analysis using real weather data
        """
        # Get game situations with weather data
        weather_games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                GameSituation.weather_condition.isnot(None)
            )
        ).all()
        
        if not weather_games:
            return self._generate_default_weather_analysis()
        
        # Group by weather conditions
        weather_performance = defaultdict(list)
        for game in weather_games:
            weather_performance[game.weather_condition].append({
                'fantasy_points': game.fantasy_points,
                'temperature': game.temperature,
                'wind_speed': game.wind_speed,
                'humidity': game.humidity
            })
        
        weather_analysis = {}
        for condition, games in weather_performance.items():
            if len(games) >= 2:
                points = [g['fantasy_points'] for g in games if g['fantasy_points']]
                if points:
                    weather_analysis[condition] = {
                        'avg_points': round(statistics.mean(points), 2),
                        'games': len(points),
                        'avg_temperature': round(statistics.mean([g['temperature'] for g in games if g['temperature']]), 1) if any(g['temperature'] for g in games) else None,
                        'avg_wind': round(statistics.mean([g['wind_speed'] for g in games if g['wind_speed']]), 1) if any(g['wind_speed'] for g in games) else None,
                        'consistency': round(1 - (statistics.stdev(points) / statistics.mean(points)), 3) if statistics.mean(points) > 0 else 0
                    }
        
        # Temperature analysis
        temp_analysis = await self._analyze_temperature_impact(weather_games)
        
        # Wind analysis
        wind_analysis = await self._analyze_wind_impact(weather_games)
        
        # Dome vs outdoor analysis
        dome_outdoor_analysis = await self._analyze_dome_vs_outdoor(player_id)
        
        # Weather sensitivity score
        sensitivity_score = self._calculate_weather_sensitivity(weather_analysis)
        
        return {
            'weather_condition_performance': weather_analysis,
            'temperature_analysis': temp_analysis,
            'wind_analysis': wind_analysis,
            'dome_vs_outdoor': dome_outdoor_analysis,
            'weather_sensitivity': sensitivity_score,
            'upcoming_weather_impact': await self._forecast_weather_impact(player_id),
            'recommendations': self._generate_weather_recommendations(weather_analysis, sensitivity_score)
        }
    
    async def _enhanced_opponent_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Advanced opponent strength analysis using defensive rankings
        """
        # Get game situations with opponent data
        opponent_games = self.db.query(GameSituation).filter(
            GameSituation.player_id == player_id
        ).all()
        
        if not opponent_games:
            return self._generate_default_opponent_analysis()
        
        # Get player position for relevant defensive rankings
        player = self.db.query(Player).filter(Player.id == player_id).first()
        position = player.position.value if player and player.position else 'FLEX'
        
        # Analyze performance vs different defensive strength levels
        def_strength_performance = {
            'elite_defense': [],      # Top 8 defenses
            'good_defense': [],       # 9-16 defenses
            'average_defense': [],    # 17-24 defenses
            'weak_defense': []        # 25-32 defenses
        }
        
        for game in opponent_games:
            if game.opponent_def_rank_vs_position:
                rank = game.opponent_def_rank_vs_position
                if rank <= 8:
                    def_strength_performance['elite_defense'].append(game.fantasy_points)
                elif rank <= 16:
                    def_strength_performance['good_defense'].append(game.fantasy_points)
                elif rank <= 24:
                    def_strength_performance['average_defense'].append(game.fantasy_points)
                else:
                    def_strength_performance['weak_defense'].append(game.fantasy_points)
        
        # Calculate statistics for each strength level
        opponent_analysis = {}
        for strength, points in def_strength_performance.items():
            if points and len(points) >= 2:
                opponent_analysis[strength] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points),
                    'consistency': round(1 - (statistics.stdev(points) / statistics.mean(points)), 3) if statistics.mean(points) > 0 else 0,
                    'ceiling': max(points),
                    'floor': min(points)
                }
        
        # Matchup dependency score
        matchup_dependency = self._calculate_matchup_dependency(opponent_analysis)
        
        # Division rival analysis
        division_analysis = await self._analyze_division_matchups(player_id)
        
        # Upcoming opponent analysis
        upcoming_opponents = await self._analyze_upcoming_opponents(player.team if player else "", position)
        
        return {
            'defense_strength_performance': opponent_analysis,
            'matchup_dependency': matchup_dependency,
            'division_rival_performance': division_analysis,
            'upcoming_opponents': upcoming_opponents,
            'optimal_matchups': self._identify_optimal_matchups(opponent_analysis),
            'avoid_matchups': self._identify_avoid_matchups(opponent_analysis),
            'recommendations': self._generate_opponent_recommendations(opponent_analysis, matchup_dependency)
        }
    
    async def _enhanced_game_script_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Advanced game script analysis with pace and situational factors
        """
        # Get game situations with game script data
        script_games = self.db.query(GameSituation).filter(
            GameSituation.player_id == player_id
        ).all()
        
        if not script_games:
            return self._generate_default_game_script_analysis()
        
        # Group by game script
        script_performance = defaultdict(list)
        for game in script_games:
            if game.game_script:
                script_performance[game.game_script].append({
                    'fantasy_points': game.fantasy_points,
                    'targets': game.targets,
                    'carries': game.carries,
                    'snap_percentage': game.snap_percentage,
                    'point_differential': game.point_differential,
                    'pace_of_play': game.pace_of_play
                })
        
        script_analysis = {}
        for script, games in script_performance.items():
            if games and len(games) >= 2:
                points = [g['fantasy_points'] for g in games if g['fantasy_points']]
                if points:
                    script_analysis[script] = {
                        'avg_points': round(statistics.mean(points), 2),
                        'games': len(points),
                        'avg_targets': round(statistics.mean([g['targets'] for g in games if g['targets']]), 1) if any(g['targets'] for g in games) else 0,
                        'avg_carries': round(statistics.mean([g['carries'] for g in games if g['carries']]), 1) if any(g['carries'] for g in games) else 0,
                        'avg_snap_pct': round(statistics.mean([g['snap_percentage'] for g in games if g['snap_percentage']]), 1) if any(g['snap_percentage'] for g in games) else 0,
                        'consistency': round(1 - (statistics.stdev(points) / statistics.mean(points)), 3) if statistics.mean(points) > 0 else 0
                    }
        
        # Pace of play analysis
        pace_analysis = await self._analyze_pace_impact(script_games)
        
        # Garbage time analysis
        garbage_time_analysis = await self._analyze_garbage_time_impact(player_id)
        
        # Red zone and goal line analysis
        red_zone_analysis = await self._analyze_red_zone_usage(player_id)
        
        return {
            'game_script_performance': script_analysis,
            'pace_of_play_impact': pace_analysis,
            'garbage_time_performance': garbage_time_analysis,
            'red_zone_analysis': red_zone_analysis,
            'script_dependency': self._calculate_script_dependency(script_analysis),
            'optimal_game_scripts': self._identify_optimal_scripts(script_analysis),
            'recommendations': self._generate_script_recommendations(script_analysis, pace_analysis)
        }
    
    async def _enhanced_venue_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Enhanced venue-specific analysis with stadium characteristics
        """
        # Get venue data for games
        venue_games = self.db.query(GameSituation).filter(
            GameSituation.player_id == player_id
        ).all()
        
        venue_performance = defaultdict(list)
        for game in venue_games:
            if game.venue_name:
                venue_performance[game.venue_name].append({
                    'fantasy_points': game.fantasy_points,
                    'venue_type': game.venue_type.value if game.venue_type else None,
                    'elevation': None,  # Would be joined from VenueData
                    'surface_type': None  # Would be joined from VenueData
                })
        
        # Analyze by venue type
        venue_type_analysis = defaultdict(list)
        for venue, games in venue_performance.items():
            for game in games:
                if game.get('venue_type'):
                    venue_type_analysis[game['venue_type']].append(game['fantasy_points'])
        
        venue_analysis = {}
        for venue_type, points in venue_type_analysis.items():
            if points and len(points) >= 2:
                venue_analysis[venue_type] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points),
                    'consistency': round(1 - (statistics.stdev(points) / statistics.mean(points)), 3) if statistics.mean(points) > 0 else 0
                }
        
        # High altitude analysis
        altitude_analysis = await self._analyze_altitude_impact(player_id)
        
        # Surface type analysis
        surface_analysis = await self._analyze_surface_impact(player_id)
        
        return {
            'venue_type_performance': venue_analysis,
            'altitude_impact': altitude_analysis,
            'surface_impact': surface_analysis,
            'venue_recommendations': self._generate_venue_recommendations(venue_analysis)
        }
    
    async def _prime_time_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Analyze performance in prime time vs regular games
        """
        prime_time_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_prime_time == True)
        ).all()
        
        regular_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_prime_time == False)
        ).all()
        
        prime_time_stats = self._calculate_situational_stats(prime_time_games)
        regular_stats = self._calculate_situational_stats(regular_games)
        
        return {
            'prime_time_performance': prime_time_stats,
            'regular_time_performance': regular_stats,
            'prime_time_advantage': prime_time_stats['avg_points'] - regular_stats['avg_points'] if prime_time_stats['games'] > 0 and regular_stats['games'] > 0 else 0,
            'sample_sizes': {
                'prime_time': prime_time_stats['games'],
                'regular': regular_stats['games']
            },
            'recommendations': self._generate_prime_time_recommendations(prime_time_stats, regular_stats)
        }
    
    async def _rivalry_game_analysis(self, player_id: int) -> Dict[str, Any]:
        """
        Analyze performance in division rivalry games
        """
        rivalry_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_division_rival == True)
        ).all()
        
        non_rivalry_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_division_rival == False)
        ).all()
        
        rivalry_stats = self._calculate_situational_stats(rivalry_games)
        non_rivalry_stats = self._calculate_situational_stats(non_rivalry_games)
        
        return {
            'rivalry_performance': rivalry_stats,
            'non_rivalry_performance': non_rivalry_stats,
            'rivalry_impact': rivalry_stats['avg_points'] - non_rivalry_stats['avg_points'] if rivalry_stats['games'] > 0 and non_rivalry_stats['games'] > 0 else 0,
            'emotional_factor': self._assess_rivalry_emotional_factor(rivalry_stats, non_rivalry_stats),
            'recommendations': self._generate_rivalry_recommendations(rivalry_stats, non_rivalry_stats)
        }
    
    # Helper methods for enhanced analysis
    def _calculate_situational_stats(self, games: List[GameSituation]) -> Dict[str, Any]:
        """Calculate comprehensive statistics for a set of games"""
        if not games:
            return {
                'avg_points': 0.0,
                'games': 0,
                'total_points': 0.0,
                'consistency': 0.0,
                'ceiling': 0.0,
                'floor': 0.0,
                'std_dev': 0.0
            }
        
        points = [game.fantasy_points for game in games if game.fantasy_points is not None]
        
        if not points:
            return {
                'avg_points': 0.0,
                'games': len(games),
                'total_points': 0.0,
                'consistency': 0.0,
                'ceiling': 0.0,
                'floor': 0.0,
                'std_dev': 0.0
            }
        
        avg_points = statistics.mean(points)
        std_dev = statistics.stdev(points) if len(points) > 1 else 0.0
        
        return {
            'avg_points': round(avg_points, 2),
            'games': len(points),
            'total_points': round(sum(points), 2),
            'consistency': round(1 - (std_dev / avg_points), 3) if avg_points > 0 else 0.0,
            'ceiling': round(max(points), 2),
            'floor': round(min(points), 2),
            'std_dev': round(std_dev, 2)
        }
    
    def _calculate_confidence(self, sample_size: int) -> str:
        """Calculate confidence level based on sample size"""
        if sample_size >= 20:
            return "HIGH"
        elif sample_size >= 10:
            return "MEDIUM"
        elif sample_size >= 5:
            return "LOW"
        else:
            return "VERY_LOW"
    
    async def _analyze_travel_impact(self, player_id: int, away_games: List[GameSituation]) -> Dict[str, Any]:
        """
        CATEGORY: Insufficient data (genuinely not feasible this pass).
        Real travel-distance impact requires the distance between each
        away venue and the player's home stadium -- i.e. per-stadium
        latitude/longitude and a haversine calculation. VenueData (this
        module's own venue table) has no coordinate columns at all, and
        no other model in this app stores stadium locations either. Adding
        that is new reference-data infrastructure (32+ stadium coordinates
        plus a distance calculator), not a bug fix, so rather than keep the
        old hardcoded "10.5 vs 12.3, MODERATE fatigue" shown for every
        player, this honestly reports the gap.
        """
        return {
            'cross_country_games': None,
            'avg_points_long_travel': None,
            'avg_points_short_travel': None,
            'travel_fatigue_factor': "INSUFFICIENT_DATA",
            'data_confidence': 'insufficient',
            'note': 'Stadium location/coordinate data is not available anywhere in this app, so travel distance cannot be computed.'
        }
    
    def _generate_default_weather_analysis(self) -> Dict[str, Any]:
        """Generate default weather analysis when no data available"""
        return {
            'weather_condition_performance': {},
            'temperature_analysis': {'insufficient_data': True},
            'wind_analysis': {'insufficient_data': True},
            'dome_vs_outdoor': {'insufficient_data': True},
            'weather_sensitivity': 'UNKNOWN',
            'recommendations': ['Insufficient weather data for analysis']
        }
    
    def _generate_default_opponent_analysis(self) -> Dict[str, Any]:
        """Generate default opponent analysis when no data available"""
        return {
            'defense_strength_performance': {},
            'matchup_dependency': 'UNKNOWN',
            'division_rival_performance': {'insufficient_data': True},
            'upcoming_opponents': [],
            'recommendations': ['Insufficient opponent data for analysis']
        }
    
    def _generate_default_game_script_analysis(self) -> Dict[str, Any]:
        """Generate default game script analysis when no data available"""
        return {
            'game_script_performance': {},
            'pace_of_play_impact': {'insufficient_data': True},
            'garbage_time_performance': {'insufficient_data': True},
            'red_zone_analysis': {'insufficient_data': True},
            'recommendations': ['Insufficient game script data for analysis']
        }
    
    async def _analyze_temperature_impact(self, weather_games: List[GameSituation]) -> Dict[str, Any]:
        """Analyze temperature impact on performance"""
        temp_buckets = {
            'cold': [],      # < 40°F
            'cool': [],      # 40-60°F
            'moderate': [],  # 60-75°F
            'warm': [],      # 75-85°F
            'hot': []        # > 85°F
        }
        
        for game in weather_games:
            if game.temperature is not None and game.fantasy_points is not None:
                temp = game.temperature
                if temp < 40:
                    temp_buckets['cold'].append(game.fantasy_points)
                elif temp < 60:
                    temp_buckets['cool'].append(game.fantasy_points)
                elif temp < 75:
                    temp_buckets['moderate'].append(game.fantasy_points)
                elif temp < 85:
                    temp_buckets['warm'].append(game.fantasy_points)
                else:
                    temp_buckets['hot'].append(game.fantasy_points)
        
        temp_analysis = {}
        for bucket, points in temp_buckets.items():
            if points and len(points) >= 2:
                temp_analysis[bucket] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points)
                }
        
        return temp_analysis
    
    async def _analyze_wind_impact(self, weather_games: List[GameSituation]) -> Dict[str, Any]:
        """Analyze wind speed impact on performance"""
        wind_buckets = {
            'calm': [],      # < 5 mph
            'light': [],     # 5-10 mph
            'moderate': [],  # 10-15 mph
            'strong': [],    # 15-20 mph
            'very_strong': [] # > 20 mph
        }
        
        for game in weather_games:
            if game.wind_speed is not None and game.fantasy_points is not None:
                wind = game.wind_speed
                if wind < 5:
                    wind_buckets['calm'].append(game.fantasy_points)
                elif wind < 10:
                    wind_buckets['light'].append(game.fantasy_points)
                elif wind < 15:
                    wind_buckets['moderate'].append(game.fantasy_points)
                elif wind < 20:
                    wind_buckets['strong'].append(game.fantasy_points)
                else:
                    wind_buckets['very_strong'].append(game.fantasy_points)
        
        wind_analysis = {}
        for bucket, points in wind_buckets.items():
            if points and len(points) >= 2:
                wind_analysis[bucket] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points)
                }
        
        return wind_analysis
    
    async def _analyze_dome_vs_outdoor(self, player_id: int) -> Dict[str, Any]:
        """Analyze dome vs outdoor performance"""
        dome_games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                GameSituation.venue_type == VENUE_TYPES['DOME']
            )
        ).all()
        
        outdoor_games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                GameSituation.venue_type == VENUE_TYPES['OUTDOOR']
            )
        ).all()
        
        dome_stats = self._calculate_situational_stats(dome_games)
        outdoor_stats = self._calculate_situational_stats(outdoor_games)
        
        return {
            'dome_performance': dome_stats,
            'outdoor_performance': outdoor_stats,
            'dome_advantage': dome_stats['avg_points'] - outdoor_stats['avg_points'] if dome_stats['games'] > 0 and outdoor_stats['games'] > 0 else 0
        }
    
    def _calculate_weather_sensitivity(self, weather_analysis: Dict) -> str:
        """Calculate overall weather sensitivity score"""
        if not weather_analysis:
            return "UNKNOWN"
        
        # Simple heuristic - compare variance across conditions
        point_values = [condition['avg_points'] for condition in weather_analysis.values()]
        if len(point_values) < 2:
            return "LOW"
        
        variance = statistics.stdev(point_values) if len(point_values) > 1 else 0
        if variance > 3:
            return "HIGH"
        elif variance > 1.5:
            return "MEDIUM"
        else:
            return "LOW"
    
    async def _forecast_weather_impact(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Insufficient data (genuinely not feasible this pass).
        A real weather *forecast* (as opposed to historical weather) needs
        a live weather API integration -- this app has no such integration
        anywhere (NFLGame.weather_conditions is a real column, but nothing
        ever writes a forecast into it; there's no scheduled sync). Rather
        than keep the old hardcoded "CLEAR / RAIN / DOME" 3-week preview
        shown for every player, this reports the gap honestly.
        """
        return {
            'next_game': None,
            'upcoming_games': [],
            'data_confidence': 'insufficient',
            'note': 'No weather forecast integration exists in this app yet.'
        }
    
    def _calculate_matchup_dependency(self, opponent_analysis: Dict) -> str:
        """Calculate how matchup-dependent a player is"""
        if not opponent_analysis or len(opponent_analysis) < 3:
            return "UNKNOWN"
        
        point_values = [data['avg_points'] for data in opponent_analysis.values()]
        variance = statistics.stdev(point_values) if len(point_values) > 1 else 0
        
        if variance > 4:
            return "HIGH"
        elif variance > 2:
            return "MEDIUM"
        else:
            return "LOW"
    
    async def _analyze_division_matchups(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Computed. Real division-rival vs non-division split from
        this player's own logged GameSituation rows (is_division_rival is a
        real column -- the same one _rivalry_game_analysis already uses
        elsewhere in this class). Previously this ignored player_id
        entirely and returned a fixed 11.2/12.8/-1.6/6 for everyone.
        """
        division_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_division_rival == True)
        ).all()
        non_division_games = self.db.query(GameSituation).filter(
            and_(GameSituation.player_id == player_id, GameSituation.is_division_rival == False)
        ).all()

        division_stats = self._calculate_situational_stats(division_games)
        non_division_stats = self._calculate_situational_stats(non_division_games)

        if division_stats['games'] < 2 or non_division_stats['games'] < 2:
            return {
                'division_avg': None,
                'non_division_avg': None,
                'rivalry_factor': None,
                'games_analyzed': division_stats['games'] + non_division_stats['games'],
                'data_confidence': 'insufficient',
                'note': 'Not enough logged division-rival games for this player yet.'
            }

        return {
            'division_avg': division_stats['avg_points'],
            'non_division_avg': non_division_stats['avg_points'],
            'rivalry_factor': round(division_stats['avg_points'] - non_division_stats['avg_points'], 2),
            'games_analyzed': division_stats['games'] + non_division_stats['games'],
            'data_confidence': 'computed'
        }

    async def _analyze_upcoming_opponents(self, team: str, position: str = 'FLEX') -> List[Dict[str, Any]]:
        """
        CATEGORY: Computed. Real upcoming opponents/defensive ranks sourced
        from the NFLGame / DefensiveMatchupRanking tables via
        MatchupAnalysisService -- the same real schedule infrastructure the
        Matchup Analysis and Waiver Wire features already use. Previously
        this returned the same three DAL/NYG/WAS opponents for every team
        regardless of who was actually asked about. Honestly returns an
        empty list rather than mock opponents when no schedule rows are
        synced for this team yet.
        """
        matchup_service = MatchupAnalysisService(self.db)
        current_week = matchup_service.get_current_week()

        games = self.db.query(NFLGame).filter(
            and_(
                NFLGame.season == 2024,
                NFLGame.week.between(current_week, current_week + 2),
                or_(NFLGame.home_team == team, NFLGame.away_team == team)
            )
        ).order_by(NFLGame.week).all()

        opponents = []
        for game in games:
            opponent = game.away_team if game.home_team == team else game.home_team
            rating = matchup_service.get_defensive_matchup_rating(opponent, position, game.week)
            def_rank = rating.get('rank_vs_position')
            opponents.append({
                'week': game.week,
                'opponent': opponent,
                'def_rank': def_rank,
                'difficulty': 'INSUFFICIENT_DATA' if def_rank is None or rating.get('confidence') == 'Low' else (
                    'EASY' if def_rank >= 25 else 'DIFFICULT' if def_rank <= 8 else 'MODERATE'
                )
            })
        return opponents
    
    def _identify_optimal_matchups(self, opponent_analysis: Dict) -> List[str]:
        """Identify optimal matchup types"""
        optimal = []
        for strength, data in opponent_analysis.items():
            if data['avg_points'] > 12:  # Threshold for good performance
                optimal.append(strength)
        return optimal
    
    def _identify_avoid_matchups(self, opponent_analysis: Dict) -> List[str]:
        """Identify matchups to avoid"""
        avoid = []
        for strength, data in opponent_analysis.items():
            if data['avg_points'] < 8:  # Threshold for poor performance
                avoid.append(strength)
        return avoid
    
    async def _analyze_pace_impact(self, script_games: List[GameSituation]) -> Dict[str, Any]:
        """Analyze impact of game pace on performance"""
        pace_buckets = {
            'slow': [],      # < 60 plays/game
            'average': [],   # 60-70 plays/game
            'fast': []       # > 70 plays/game
        }
        
        for game in script_games:
            if game.total_plays and game.fantasy_points is not None:
                plays = game.total_plays
                if plays < 60:
                    pace_buckets['slow'].append(game.fantasy_points)
                elif plays < 70:
                    pace_buckets['average'].append(game.fantasy_points)
                else:
                    pace_buckets['fast'].append(game.fantasy_points)
        
        pace_analysis = {}
        for pace, points in pace_buckets.items():
            if points and len(points) >= 2:
                pace_analysis[pace] = {
                    'avg_points': round(statistics.mean(points), 2),
                    'games': len(points)
                }
        
        return pace_analysis
    
    async def _analyze_garbage_time_impact(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Heuristic. This app has no per-quarter play log, so "garbage
        time" (last-minute snaps in a decided game) can't be isolated
        directly. As a real, per-player proxy, we classify this player's
        logged games by GameSituation.game_script -- BLOWOUT_WIN/BLOWOUT_LOSS
        games are the ones where garbage-time snaps would occur -- and
        compare fantasy output there against closer games. Real data, but a
        stand-in for true 4th-quarter garbage-time detection.
        """
        blowout_games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                GameSituation.game_script.in_([GAME_SCRIPTS['BLOWOUT_WIN'], GAME_SCRIPTS['BLOWOUT_LOSS']])
            )
        ).all()
        other_games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                GameSituation.game_script.isnot(None),
                ~GameSituation.game_script.in_([GAME_SCRIPTS['BLOWOUT_WIN'], GAME_SCRIPTS['BLOWOUT_LOSS']])
            )
        ).all()

        blowout_stats = self._calculate_situational_stats(blowout_games)
        other_stats = self._calculate_situational_stats(other_games)

        if blowout_stats['games'] < 2 or other_stats['games'] < 2:
            return {
                'garbage_time_boost': None,
                'avg_boost': None,
                'games_with_boost': blowout_stats['games'],
                'total_games': blowout_stats['games'] + other_stats['games'],
                'data_confidence': 'insufficient',
                'note': 'Not enough logged blowout-game data for this player yet.'
            }

        avg_boost = round(blowout_stats['avg_points'] - other_stats['avg_points'], 2)
        return {
            'garbage_time_boost': avg_boost > 0,
            'avg_boost': avg_boost,
            'games_with_boost': blowout_stats['games'],
            'total_games': blowout_stats['games'] + other_stats['games'],
            'data_confidence': 'heuristic'
        }

    async def _analyze_red_zone_usage(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Computed. Real per-game red_zone_targets/goal_line_carries
        columns on GameSituation (this player's own logged games), instead
        of the previous fixed 1.2/0.8/0.65/MEDIUM shown for every player.
        """
        games = self.db.query(GameSituation).filter(
            and_(
                GameSituation.player_id == player_id,
                or_(GameSituation.red_zone_targets.isnot(None), GameSituation.goal_line_carries.isnot(None))
            )
        ).all()

        if len(games) < 2:
            return {
                'red_zone_targets_per_game': None,
                'goal_line_carries_per_game': None,
                'red_zone_efficiency': None,
                'touchdown_dependency': 'INSUFFICIENT_DATA',
                'data_confidence': 'insufficient',
                'note': 'Not enough logged red-zone usage data for this player yet.'
            }

        rz_targets = [g.red_zone_targets for g in games if g.red_zone_targets is not None]
        gl_carries = [g.goal_line_carries for g in games if g.goal_line_carries is not None]
        avg_rz = round(statistics.mean(rz_targets), 2) if rz_targets else 0.0
        avg_gl = round(statistics.mean(gl_carries), 2) if gl_carries else 0.0
        total_opportunities = avg_rz + avg_gl
        dependency = "HIGH" if total_opportunities >= 2 else "MEDIUM" if total_opportunities >= 1 else "LOW"

        return {
            'red_zone_targets_per_game': avg_rz,
            'goal_line_carries_per_game': avg_gl,
            'games_analyzed': len(games),
            'touchdown_dependency': dependency,
            'data_confidence': 'computed'
        }
    
    def _calculate_script_dependency(self, script_analysis: Dict) -> str:
        """Calculate how game script dependent a player is"""
        if not script_analysis or len(script_analysis) < 2:
            return "UNKNOWN"
        
        point_values = [data['avg_points'] for data in script_analysis.values()]
        variance = statistics.stdev(point_values) if len(point_values) > 1 else 0
        
        if variance > 3:
            return "HIGH"
        elif variance > 1.5:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _identify_optimal_scripts(self, script_analysis: Dict) -> List[str]:
        """Identify optimal game scripts for the player"""
        optimal = []
        for script, data in script_analysis.items():
            if data['avg_points'] > 12:  # Threshold for good performance
                optimal.append(script)
        return optimal
    
    HIGH_ALTITUDE_FEET = 4000.0  # Denver/Mexico City-level elevation threshold

    async def _analyze_altitude_impact(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Computed. Real join between this player's logged games
        (GameSituation.venue_name) and VenueData.elevation, instead of the
        previous fixed 12.1/10.8/-1.3 shown for every player.
        """
        games = self.db.query(GameSituation, VenueData).join(
            VenueData, GameSituation.venue_name == VenueData.venue_name
        ).filter(
            and_(GameSituation.player_id == player_id, VenueData.elevation.isnot(None))
        ).all()

        high_altitude_points = [gs.fantasy_points for gs, v in games if v.elevation >= self.HIGH_ALTITUDE_FEET and gs.fantasy_points is not None]
        sea_level_points = [gs.fantasy_points for gs, v in games if v.elevation < self.HIGH_ALTITUDE_FEET and gs.fantasy_points is not None]

        if len(high_altitude_points) < 1 or len(sea_level_points) < 2:
            return {
                'high_altitude_games': len(high_altitude_points),
                'sea_level_avg': None,
                'high_altitude_avg': None,
                'altitude_impact': None,
                'data_confidence': 'insufficient',
                'note': 'Not enough logged high-altitude venue games for this player yet (needs GameSituation rows joined to VenueData.elevation).'
            }

        sea_level_avg = round(statistics.mean(sea_level_points), 2)
        high_altitude_avg = round(statistics.mean(high_altitude_points), 2)
        return {
            'high_altitude_games': len(high_altitude_points),
            'sea_level_avg': sea_level_avg,
            'high_altitude_avg': high_altitude_avg,
            'altitude_impact': round(high_altitude_avg - sea_level_avg, 2),
            'data_confidence': 'computed'
        }

    async def _analyze_surface_impact(self, player_id: int) -> Dict[str, Any]:
        """
        CATEGORY: Computed. Real join between this player's logged games
        and VenueData.surface_type, instead of the previous fixed
        12.3/11.8/GRASS/LOW shown for every player. "injury_risk_factor" is
        dropped rather than fabricated -- this app has no data linking
        surface type to this player's own injury history.
        """
        games = self.db.query(GameSituation, VenueData).join(
            VenueData, GameSituation.venue_name == VenueData.venue_name
        ).filter(
            and_(GameSituation.player_id == player_id, VenueData.surface_type.isnot(None))
        ).all()

        grass_points = [gs.fantasy_points for gs, v in games if v.surface_type and 'grass' in v.surface_type.lower() and gs.fantasy_points is not None]
        turf_points = [gs.fantasy_points for gs, v in games if v.surface_type and 'turf' in v.surface_type.lower() and gs.fantasy_points is not None]

        if len(grass_points) < 2 or len(turf_points) < 2:
            return {
                'grass_avg': None,
                'turf_avg': None,
                'surface_preference': 'INSUFFICIENT_DATA',
                'data_confidence': 'insufficient',
                'note': 'Not enough logged games with known playing surface for this player yet.'
            }

        grass_avg = round(statistics.mean(grass_points), 2)
        turf_avg = round(statistics.mean(turf_points), 2)
        return {
            'grass_avg': grass_avg,
            'turf_avg': turf_avg,
            'surface_preference': 'GRASS' if grass_avg >= turf_avg else 'TURF',
            'data_confidence': 'computed'
        }
    
    def _assess_rivalry_emotional_factor(self, rivalry_stats: Dict, non_rivalry_stats: Dict) -> str:
        """Assess emotional factor impact in rivalry games"""
        if rivalry_stats['games'] < 3:
            return "INSUFFICIENT_DATA"
        
        variance_ratio = rivalry_stats['std_dev'] / non_rivalry_stats['std_dev'] if non_rivalry_stats['std_dev'] > 0 else 1
        
        if variance_ratio > 1.5:
            return "HIGH_VARIANCE"
        elif variance_ratio > 1.2:
            return "MODERATE_VARIANCE"
        else:
            return "CONSISTENT"
    
    # Recommendation generation methods
    def _generate_home_away_recommendations(self, home_stats: Dict, away_stats: Dict, venue_analysis: Dict) -> List[str]:
        """Generate home/away recommendations"""
        recommendations = []
        
        if home_stats['avg_points'] > away_stats['avg_points'] + 2:
            recommendations.append("Strong home field advantage - prioritize home games")
        elif away_stats['avg_points'] > home_stats['avg_points'] + 2:
            recommendations.append("Road warrior - performs better away from home")
        else:
            recommendations.append("Location neutral - similar performance home and away")
        
        if venue_analysis:
            best_venue = max(venue_analysis.items(), key=lambda x: x[1]['avg_points'])
            recommendations.append(f"Best venue: {best_venue[0]} ({best_venue[1]['avg_points']} avg)")
        
        return recommendations
    
    def _generate_weather_recommendations(self, weather_analysis: Dict, sensitivity: str) -> List[str]:
        """Generate weather-based recommendations"""
        recommendations = []
        
        if sensitivity == "HIGH":
            recommendations.append("High weather sensitivity - monitor forecasts closely")
        elif sensitivity == "LOW":
            recommendations.append("Weather resistant - minimal impact from conditions")
        
        if weather_analysis:
            best_condition = max(weather_analysis.items(), key=lambda x: x[1]['avg_points'])
            recommendations.append(f"Optimal conditions: {best_condition[0]} ({best_condition[1]['avg_points']} avg)")
        
        return recommendations
    
    def _generate_opponent_recommendations(self, opponent_analysis: Dict, dependency: str) -> List[str]:
        """Generate opponent-based recommendations"""
        recommendations = []
        
        if dependency == "HIGH":
            recommendations.append("Highly matchup dependent - target favorable opponents")
        elif dependency == "LOW":
            recommendations.append("Matchup independent - consistent across opponents")
        
        optimal_matchups = self._identify_optimal_matchups(opponent_analysis)
        if optimal_matchups:
            recommendations.append(f"Target: {', '.join(optimal_matchups)} defenses")
        
        return recommendations
    
    def _generate_script_recommendations(self, script_analysis: Dict, pace_analysis: Dict) -> List[str]:
        """Generate game script recommendations"""
        recommendations = []
        
        optimal_scripts = self._identify_optimal_scripts(script_analysis)
        if optimal_scripts:
            recommendations.append(f"Optimal game scripts: {', '.join(optimal_scripts)}")
        
        if pace_analysis and 'fast' in pace_analysis:
            if pace_analysis['fast']['avg_points'] > 12:
                recommendations.append("Benefits from high-pace games")
        
        return recommendations
    
    def _generate_venue_recommendations(self, venue_analysis: Dict) -> List[str]:
        """Generate venue-based recommendations"""
        recommendations = []
        
        if 'DOME' in venue_analysis and 'OUTDOOR' in venue_analysis:
            dome_avg = venue_analysis['DOME']['avg_points']
            outdoor_avg = venue_analysis['OUTDOOR']['avg_points']
            
            if dome_avg > outdoor_avg + 1:
                recommendations.append("Dome preferred - benefits from controlled environment")
            elif outdoor_avg > dome_avg + 1:
                recommendations.append("Outdoor preferred - thrives in natural elements")
        
        return recommendations
    
    def _generate_prime_time_recommendations(self, prime_stats: Dict, regular_stats: Dict) -> List[str]:
        """Generate prime time recommendations"""
        recommendations = []
        
        if prime_stats['games'] >= 3:
            if prime_stats['avg_points'] > regular_stats['avg_points'] + 1:
                recommendations.append("Prime time performer - rises to occasion")
            elif regular_stats['avg_points'] > prime_stats['avg_points'] + 1:
                recommendations.append("May struggle in prime time spotlight")
            else:
                recommendations.append("Consistent regardless of game time")
        else:
            recommendations.append("Limited prime time sample size")
        
        return recommendations
    
    def _generate_rivalry_recommendations(self, rivalry_stats: Dict, non_rivalry_stats: Dict) -> List[str]:
        """Generate rivalry game recommendations"""
        recommendations = []
        
        if rivalry_stats['games'] >= 3:
            if rivalry_stats['avg_points'] > non_rivalry_stats['avg_points'] + 1:
                recommendations.append("Thrives in rivalry games - emotional boost")
            elif non_rivalry_stats['avg_points'] > rivalry_stats['avg_points'] + 1:
                recommendations.append("May be affected by rivalry pressure")
            else:
                recommendations.append("Consistent in rivalry games")
        else:
            recommendations.append("Limited rivalry game sample")
        
        return recommendations
    
    async def _generate_comprehensive_insights(self, player_id: int) -> List[str]:
        """Generate comprehensive situational insights"""
        insights = []
        
        # Get trend data
        trends = self.db.query(SituationalTrend).filter(
            SituationalTrend.player_id == player_id
        ).all()
        
        for trend in trends:
            if trend.sample_size_confidence > 0.7:  # High confidence
                if trend.avg_fantasy_points > 12:
                    insights.append(f"Strong in {trend.situation_type}: {trend.situation_value} ({trend.avg_fantasy_points:.1f} avg)")
                elif trend.avg_fantasy_points < 8:
                    insights.append(f"Struggles in {trend.situation_type}: {trend.situation_value} ({trend.avg_fantasy_points:.1f} avg)")
        
        return insights
    
    async def _forecast_upcoming_situations(self, player: Player) -> Dict[str, Any]:
        """
        CATEGORY: split. Opponent/location/defensive-rank come from the real
        NFLGame / DefensiveMatchupRanking tables via MatchupAnalysisService
        (Computed) -- the same infrastructure used elsewhere in this class.
        venue_type/expected_weather/projected_script/situational_score are
        dropped rather than fabricated: this app has no weather-forecast
        integration and no venue join wired into MatchupAnalysisService's
        schedule query, so a "situational_score" here would just be made up.
        Previously this returned the identical DAL/GB two-week preview for
        every player regardless of their actual team or schedule.
        """
        matchup_service = MatchupAnalysisService(self.db)
        matchup_info = matchup_service.analyze_player_upcoming_matchups(player, weeks_ahead=4)

        if "error" in matchup_info or not matchup_info.get("upcoming_matchups"):
            return {
                'next_4_weeks': [],
                'optimal_weeks': [],
                'caution_weeks': [],
                'overall_outlook': 'INSUFFICIENT_DATA',
                'data_confidence': 'insufficient',
                'note': 'No synced schedule data for this player yet.'
            }

        next_weeks = []
        optimal_weeks = []
        caution_weeks = []
        for game in matchup_info["upcoming_matchups"]:
            next_weeks.append({
                'week': game['week'],
                'opponent': game['opponent'],
                'location': 'HOME' if game['is_home'] else 'AWAY',
                'def_rank': game.get('opponent_rank_vs_position'),
                'matchup_rating': game.get('matchup_rating')
            })
            if game.get('matchup_rating') is not None and game['matchup_rating'] >= 7.5:
                optimal_weeks.append(game['week'])
            elif game.get('matchup_rating') is not None and game['matchup_rating'] <= 4.0:
                caution_weeks.append(game['week'])

        return {
            'next_4_weeks': next_weeks,
            'optimal_weeks': optimal_weeks,
            'caution_weeks': caution_weeks,
            'overall_outlook': matchup_info.get('outlook', 'Unknown'),
            'data_confidence': 'computed'
        }
    
    async def _generate_cross_situational_insights(self, analysis_results: List[Dict]) -> List[str]:
        """Generate insights comparing players across situations"""
        insights = []
        
        if len(analysis_results) >= 2:
            insights.append("Cross-player situational analysis completed")
            insights.append("Consider situational matchups when choosing between players")
            
            # Compare weather sensitivity
            weather_sensitive = []
            weather_resistant = []
            
            for analysis in analysis_results:
                player_name = analysis['player']['name']
                if 'weather_analysis' in analysis:
                    sensitivity = analysis['weather_analysis'].get('weather_sensitivity', 'UNKNOWN')
                    if sensitivity == 'HIGH':
                        weather_sensitive.append(player_name)
                    elif sensitivity == 'LOW':
                        weather_resistant.append(player_name)
            
            if weather_sensitive:
                insights.append(f"Weather sensitive: {', '.join(weather_sensitive)}")
            if weather_resistant:
                insights.append(f"Weather resistant: {', '.join(weather_resistant)}")
        
        return insights
    
    async def _generate_situational_recommendations(self, analysis_results: List[Dict]) -> List[str]:
        """Generate overall situational recommendations"""
        recommendations = []
        
        for analysis in analysis_results:
            player_name = analysis['player']['name']
            
            # Compile best situations
            best_situations = []
            
            # Check home/away preference
            if 'home_away_analysis' in analysis:
                home_away = analysis['home_away_analysis']
                if home_away.get('advantage') == 'HOME':
                    best_situations.append('home games')
                elif home_away.get('advantage') == 'AWAY':
                    best_situations.append('away games')
            
            # Check weather preferences
            if 'weather_analysis' in analysis:
                weather = analysis['weather_analysis']
                if weather.get('dome_vs_outdoor', {}).get('dome_advantage', 0) > 1:
                    best_situations.append('dome games')
            
            if best_situations:
                recommendations.append(f"{player_name}: Optimal in {', '.join(best_situations)}")
        
        recommendations.append("Monitor upcoming situational factors when making lineup decisions")
        recommendations.append("Consider stacking players with complementary situational profiles")
        
        return recommendations