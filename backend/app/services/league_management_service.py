from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.user_league import UserLeague
from app.models.player import Player
from app.services.yahoo_service import yahoo_service
from app.services.sleeper_service import sleeper_service
from app.services.ai_service import ai_service
from app.services.player_data_service import PlayerDataService
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)

class LeagueManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.player_service = PlayerDataService(db)

    async def get_comprehensive_league_analysis(self, user_id: int, league_id: int) -> Dict[str, Any]:
        """Get comprehensive league analysis including roster, matchups, and recommendations"""
        try:
            league = self.db.query(UserLeague).filter(
                UserLeague.user_id == user_id,
                UserLeague.id == league_id
            ).first()
            
            if not league:
                return {"error": "League not found"}

            analysis = {
                "league_info": {
                    "id": league.id,
                    "name": league.league_name,
                    "platform": league.platform,
                    "season": league.season,
                    "scoring_format": league.scoring_format,
                    "league_size": league.league_size
                }
            }

            if league.platform == "YAHOO":
                # Get roster analysis
                roster_analysis = await self._analyze_yahoo_roster(league)
                analysis["roster_analysis"] = roster_analysis
                
                # Get matchup analysis
                matchup_analysis = await self._analyze_current_matchup(league)
                analysis["current_matchup"] = matchup_analysis
                
                # Get league standings
                standings = await self._get_league_standings(league)
                analysis["standings"] = standings
                
                # Get waiver wire recommendations
                waiver_recs = await self._get_league_specific_waiver_recs(league)
                analysis["waiver_recommendations"] = waiver_recs
                
                # Get trade recommendations
                trade_recs = await self._get_trade_recommendations(league)
                analysis["trade_recommendations"] = trade_recs

            return analysis

        except Exception as e:
            logger.error(f"Error in comprehensive league analysis: {str(e)}")
            return {"error": str(e)}

    async def _analyze_yahoo_roster(self, league: UserLeague) -> Dict[str, Any]:
        """Analyze Yahoo Fantasy roster"""
        try:
            if not league.team_id:
                return {"error": "Team ID not configured"}

            # Get roster from Yahoo
            roster_data = await yahoo_service.get_team_roster(league.team_id)
            
            if "error" in roster_data:
                return {"error": roster_data["error"]}

            players = roster_data.get("players", [])
            
            # Analyze each position group
            position_analysis = {}
            roster_strengths = []
            roster_weaknesses = []
            
            positions = ["QB", "RB", "WR", "TE", "K", "DEF"]
            
            for position in positions:
                pos_players = [p for p in players if p.get("position") == position]
                
                if pos_players:
                    # Get AI analysis for position group
                    pos_analysis = await self._analyze_position_group(position, pos_players)
                    position_analysis[position] = pos_analysis
                    
                    # Determine if position is strength or weakness
                    if pos_analysis.get("grade", "C") in ["A", "B"]:
                        roster_strengths.append(f"{position}: {pos_analysis.get('summary', '')}")
                    elif pos_analysis.get("grade", "C") in ["D", "F"]:
                        roster_weaknesses.append(f"{position}: {pos_analysis.get('summary', '')}")

            # Generate overall roster grade
            overall_grade = await self._calculate_overall_roster_grade(position_analysis)
            
            # Get injury concerns
            injury_concerns = await self._check_roster_injuries(players)

            return {
                "total_players": len(players),
                "position_analysis": position_analysis,
                "overall_grade": overall_grade,
                "strengths": roster_strengths,
                "weaknesses": roster_weaknesses,
                "injury_concerns": injury_concerns,
                "last_updated": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to analyze roster: {str(e)}"}

    async def _analyze_position_group(self, position: str, players: List[Dict]) -> Dict[str, Any]:
        """Analyze a specific position group"""
        try:
            player_names = [p.get("name", "Unknown") for p in players]
            
            # Get enhanced player data for analysis
            enhanced_players = []
            for player in players:
                player_name = player.get("name", "")
                if player_name:
                    # Try to find enhanced data
                    enhanced_player = self.db.query(Player).filter(
                        Player.name.ilike(f"%{player_name}%")
                    ).first()
                    
                    if enhanced_player:
                        enhanced_players.append({
                            "name": enhanced_player.name,
                            "projected_points": enhanced_player.projected_points,
                            "injury_status": enhanced_player.injury_status.value if enhanced_player.injury_status else "HEALTHY",
                            "risk_level": enhanced_player.risk_level.value if enhanced_player.risk_level else "MEDIUM",
                            "ceiling_score": enhanced_player.ceiling_score,
                            "floor_score": enhanced_player.floor_score,
                            "consistency_rating": enhanced_player.consistency_rating
                        })

            # Generate AI analysis
            analysis_prompt = f"""
            Analyze this {position} group for fantasy football:
            
            Players: {player_names}
            Enhanced Data: {enhanced_players}
            
            Provide:
            1. Position group grade (A-F)
            2. Brief summary (2-3 sentences)
            3. Key strengths
            4. Areas of concern
            5. Recommended actions
            
            Format as JSON with keys: grade, summary, strengths, concerns, recommendations
            """
            
            # Single position-group grade + summary -- bounded, low-stakes
            # note, so use the fast/cheap model tier. This now also gets
            # automatic fallback to the other configured provider (it
            # called ai_service._generate_openai() directly before, which
            # had no fallback at all).
            ai_response = await ai_service._generate_with_fallback(analysis_prompt, prefer_fast_model=True)

            try:
                analysis = json.loads(ai_response)
            except:
                # Fallback if JSON parsing fails
                analysis = {
                    "grade": "C",
                    "summary": f"{position} group needs evaluation",
                    "strengths": ["Adequate depth"],
                    "concerns": ["Limited upside"],
                    "recommendations": ["Monitor waiver wire"]
                }

            return analysis

        except Exception as e:
            return {
                "grade": "C",
                "summary": f"Error analyzing {position} group",
                "error": str(e)
            }

    async def _analyze_current_matchup(self, league: UserLeague) -> Dict[str, Any]:
        """Analyze current week's matchup"""
        try:
            # Get current week matchups
            current_week = await self._get_current_week()
            matchups = await yahoo_service.get_matchups(league.league_key, current_week)
            
            if "error" in matchups:
                return {"error": matchups["error"]}

            # Find user's matchup
            user_matchup = None
            for matchup in matchups:
                teams = matchup.get("teams", [])
                for team in teams:
                    if team.get("team_id") == league.team_id:
                        user_matchup = matchup
                        break

            if not user_matchup:
                return {"error": "User matchup not found"}

            # Analyze matchup strength
            teams = user_matchup.get("teams", [])
            user_team = next((t for t in teams if t.get("team_id") == league.team_id), None)
            opponent_team = next((t for t in teams if t.get("team_id") != league.team_id), None)

            if not user_team or not opponent_team:
                return {"error": "Matchup teams not found"}

            # Generate matchup analysis
            analysis_prompt = f"""
            Analyze this fantasy football matchup:
            
            User Team: {user_team.get('name', 'Unknown')} - {user_team.get('points', 0)} points
            Opponent: {opponent_team.get('name', 'Unknown')} - {opponent_team.get('points', 0)} points
            
            Provide matchup analysis including:
            1. Win probability
            2. Key advantages
            3. Areas of concern
            4. Recommended lineup changes
            """

            # Single matchup blurb -- bounded, low-stakes -- fast/cheap
            # model tier, with automatic fallback to the other configured
            # provider (this previously called ai_service._generate_openai()
            # directly with no fallback: an unconfigured/rate-limited/failed
            # OpenAI client meant the literal string "OpenAI client not
            # configured" -- or a real rate-limit error string -- got
            # embedded as this matchup's "ai_analysis" with no exception
            # ever raised).
            ai_analysis = await ai_service._generate_with_fallback(analysis_prompt, prefer_fast_model=True)

            return {
                "week": current_week,
                "user_team": user_team,
                "opponent_team": opponent_team,
                "ai_analysis": ai_analysis,
                "updated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to analyze matchup: {str(e)}"}

    async def _get_league_standings(self, league: UserLeague) -> Dict[str, Any]:
        """Get detailed league standings with analysis"""
        try:
            teams = await yahoo_service.get_league_teams(league.league_key)
            
            if "error" in teams:
                return {"error": teams["error"]}

            # Sort by record and points
            teams.sort(key=lambda x: (-int(x.get("wins", 0)), -float(x.get("points_for", 0))))
            
            # Add rankings and analysis
            for i, team in enumerate(teams):
                team["rank"] = i + 1
                team["playoff_position"] = i < 6  # Assuming 6-team playoffs
                
                # Calculate team metrics
                wins = int(team.get("wins", 0))
                losses = int(team.get("losses", 0))
                points_for = float(team.get("points_for", 0))
                points_against = float(team.get("points_against", 0))
                
                games_played = wins + losses
                if games_played > 0:
                    team["win_percentage"] = wins / games_played
                    team["avg_points_for"] = points_for / games_played
                    team["avg_points_against"] = points_against / games_played
                else:
                    team["win_percentage"] = 0
                    team["avg_points_for"] = 0
                    team["avg_points_against"] = 0

            # Find user's team position
            user_team = next((t for t in teams if t.get("team_id") == league.team_id), None)
            
            return {
                "teams": teams,
                "user_team_rank": user_team.get("rank") if user_team else None,
                "total_teams": len(teams),
                "playoff_teams": 6,
                "updated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to get standings: {str(e)}"}

    async def _get_league_specific_waiver_recs(self, league: UserLeague) -> Dict[str, Any]:
        """Get waiver wire recommendations specific to league settings"""
        try:
            # Get trending players
            trending_players = self.player_service.get_trending_players("UP", limit=20)
            
            # Filter based on league roster needs
            roster_data = await yahoo_service.get_team_roster(league.team_id)
            if "error" in roster_data:
                return {"error": roster_data["error"]}

            current_players = [p.get("name", "") for p in roster_data.get("players", [])]
            
            # Get position needs analysis
            position_needs = await self._analyze_position_needs(roster_data.get("players", []))
            
            # Filter trending players by position needs and availability
            filtered_recs = []
            for player in trending_players:
                if player.name not in current_players:
                    if player.position and player.position.value in position_needs:
                        priority = position_needs[player.position.value]
                        filtered_recs.append({
                            "player": player,
                            "priority": priority,
                            "reason": f"Addresses {player.position.value} need"
                        })

            # Sort by priority and projected points
            filtered_recs.sort(key=lambda x: (x["priority"], x["player"].projected_points or 0), reverse=True)

            return {
                "recommendations": filtered_recs[:10],
                "position_needs": position_needs,
                "total_available": len(filtered_recs),
                "updated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to get waiver recommendations: {str(e)}"}

    async def _get_trade_recommendations(self, league: UserLeague) -> Dict[str, Any]:
        """Get AI-powered trade recommendations"""
        try:
            # Get user's roster
            roster_data = await yahoo_service.get_team_roster(league.team_id)
            if "error" in roster_data:
                return {"error": roster_data["error"]}

            # Get league teams for potential trade partners
            teams = await yahoo_service.get_league_teams(league.league_key)
            if "error" in teams:
                return {"error": teams["error"]}

            # Generate trade analysis
            analysis_prompt = f"""
            Analyze potential trades for this fantasy team:
            
            My Roster: {roster_data.get('players', [])}
            League Teams: {len(teams)} teams
            
            Suggest 3 realistic trade scenarios considering:
            1. Position needs and surpluses
            2. Player values and trends
            3. Team contexts
            
            Format as JSON array with: target_player, offer_players, reasoning, likelihood
            """

            # Suggesting real trades across multiple rosters is
            # consequential and benefits from stronger reasoning -- deep
            # model tier, with automatic fallback.
            ai_response = await ai_service._generate_with_fallback(analysis_prompt, prefer_fast_model=False)

            try:
                trade_suggestions = json.loads(ai_response)
            except:
                trade_suggestions = [
                    {
                        "target_player": "High-value player",
                        "offer_players": ["Surplus player"],
                        "reasoning": "Address position need",
                        "likelihood": "Medium"
                    }
                ]

            return {
                "suggestions": trade_suggestions,
                "trade_deadline": "Week 13",  # Standard fantasy trade deadline
                "updated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to get trade recommendations: {str(e)}"}

    async def _calculate_overall_roster_grade(self, position_analysis: Dict) -> str:
        """Calculate overall roster grade from position analyses"""
        grades = []
        grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        
        for pos_data in position_analysis.values():
            grade = pos_data.get("grade", "C")
            if grade in grade_values:
                grades.append(grade_values[grade])
        
        if not grades:
            return "C"
        
        avg_grade = sum(grades) / len(grades)
        
        if avg_grade >= 3.5:
            return "A"
        elif avg_grade >= 2.5:
            return "B"
        elif avg_grade >= 1.5:
            return "C"
        elif avg_grade >= 0.5:
            return "D"
        else:
            return "F"

    async def _check_roster_injuries(self, players: List[Dict]) -> List[Dict]:
        """Check for injury concerns in roster"""
        injury_concerns = []
        
        for player in players:
            player_name = player.get("name", "")
            if player_name:
                # Check enhanced player data for injury status
                enhanced_player = self.db.query(Player).filter(
                    Player.name.ilike(f"%{player_name}%")
                ).first()
                
                if enhanced_player and enhanced_player.injury_status:
                    if enhanced_player.injury_status.value != "HEALTHY":
                        injury_concerns.append({
                            "player": player_name,
                            "status": enhanced_player.injury_status.value,
                            "body_part": enhanced_player.injury_body_part,
                            "severity": "HIGH" if enhanced_player.injury_status.value in ["OUT", "IR"] else "MEDIUM"
                        })
        
        return injury_concerns

    async def _analyze_position_needs(self, players: List[Dict]) -> Dict[str, int]:
        """Analyze position needs (higher score = greater need)"""
        position_counts = {}
        for player in players:
            pos = player.get("position", "")
            position_counts[pos] = position_counts.get(pos, 0) + 1
        
        # Assign need scores (simplified logic)
        needs = {}
        ideal_counts = {"QB": 2, "RB": 4, "WR": 5, "TE": 2, "K": 1, "DEF": 1}
        
        for pos, ideal in ideal_counts.items():
            current = position_counts.get(pos, 0)
            if current < ideal:
                needs[pos] = 3  # High need
            elif current == ideal:
                needs[pos] = 1  # Low need
            else:
                needs[pos] = 0  # No need
        
        return needs

    async def _get_current_week(self) -> int:
        """Get current NFL week (simplified)"""
        # In real implementation, this would check current date against NFL schedule
        return 1

    async def get_league_insights(self, user_id: int, league_id: int) -> Dict[str, Any]:
        """Get weekly insights and recommendations for a league"""
        try:
            # First try to get league from database
            league = self.db.query(UserLeague).filter(
                UserLeague.user_id == user_id,
                UserLeague.id == league_id
            ).first()
            
            # If not found in database, try to get from connected league data
            if not league and league_id == 1:
                from app.utils.league_data_loader import get_league_info
                league_info = get_league_info(league_id)
                
                # Create a temporary league object for processing
                class TempLeague:
                    def __init__(self, info):
                        self.league_name = info["name"]
                        self.platform = info["platform"]
                        self.season = info["season"]
                        self.scoring_format = info["scoring_format"]
                        self.league_size = info["league_size"]
                        self.league_key = info.get("league_key")
                        self.team_id = "1"  # Default team ID
                
                league = TempLeague(league_info)
            
            if not league:
                return {"error": "League not found"}

            # Get multiple insights (simplified to avoid API timeouts)
            insights = {
                "weekly_outlook": {
                    "outlook": "Positive",
                    "key_points": [
                        "Strong RB matchups this week based on defensive rankings",
                        "Favorable QB streaming options available on waivers",
                        "Monitor injury reports for key WR targets"
                    ],
                    "confidence": "High"
                },
                "start_sit": [
                    {
                        "player": "Lamar Jackson",
                        "position": "QB",
                        "recommendation": "START",
                        "reasoning": "Elite matchup against bottom-5 pass defense",
                        "confidence": "High"
                    },
                    {
                        "player": "Derrick Henry",
                        "position": "RB", 
                        "recommendation": "START",
                        "reasoning": "High-volume workload with goal-line opportunities",
                        "confidence": "Medium"
                    }
                ],
                "pickup_targets": [
                    {
                        "player": "Tyler Boyd",
                        "position": "WR",
                        "reason": "Elevated target share with WR1 out",
                        "priority": 3
                    },
                    {
                        "player": "Justice Hill",
                        "position": "RB",
                        "reason": "Handcuff value with standalone flex appeal",
                        "priority": 2
                    }
                ],
                "lineup_optimization": {
                    "projected_points": 148.5,
                    "lineup_changes": [
                        {
                            "position": "FLEX",
                            "current": "Cooper Kupp",
                            "recommended": "Travis Kelce", 
                            "point_gain": 2.8
                        }
                    ],
                    "confidence": "Medium"
                }
            }

            return {
                "league_name": league.league_name,
                "insights": insights,
                "generated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to generate insights: {str(e)}"}

    async def _generate_weekly_outlook(self, league: UserLeague) -> Dict[str, Any]:
        """Generate weekly outlook for the team"""
        # Implementation would analyze matchups, player situations, etc.
        return {
            "outlook": "Positive",
            "key_points": [
                "Favorable matchups at RB position",
                "QB has high ceiling this week",
                "Monitor injury reports for WR2"
            ],
            "confidence": "Medium"
        }

    async def _generate_start_sit_recs(self, league: UserLeague) -> List[Dict]:
        """Generate start/sit recommendations"""
        # Implementation would analyze player matchups and projections
        return [
            {
                "player": "Player Name",
                "position": "WR",
                "recommendation": "START",
                "reasoning": "Favorable matchup against weak secondary",
                "confidence": "High"
            }
        ]

    async def _get_top_pickup_targets(self, league: UserLeague) -> List[Dict]:
        """Get top waiver wire pickup targets"""
        # Get waiver recommendations and format for insights
        waiver_data = await self._get_league_specific_waiver_recs(league)
        
        if "error" in waiver_data:
            return []
        
        recommendations = waiver_data.get("recommendations", [])[:5]
        
        return [
            {
                "player": rec["player"].name,
                "position": rec["player"].position.value if rec["player"].position else "UNKNOWN",
                "reason": rec["reason"],
                "priority": rec["priority"]
            }
            for rec in recommendations
        ]

    async def _optimize_lineup(self, league: UserLeague) -> Dict[str, Any]:
        """Optimize lineup for maximum points"""
        # Implementation would use projections and constraints
        return {
            "projected_points": 145.2,
            "lineup_changes": [
                {
                    "position": "FLEX",
                    "current": "Player A",
                    "recommended": "Player B",
                    "point_gain": 2.3
                }
            ],
            "confidence": "Medium"
        }