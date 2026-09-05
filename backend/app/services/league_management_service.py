from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.user_league import UserLeague
from app.models.player import Player
from app.services.yahoo_service import yahoo_service
from app.services.sleeper_service import sleeper_service
from app.services.ai_service import ai_service
from app.services.player_data_service import PlayerDataService
from app.services import roster_grading
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

            if league.platform.value.upper() == "YAHOO":
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
            else:
                # ESPN/Sleeper roster/matchup/standings/waiver/trade analysis
                # doesn't exist yet -- every helper above (_analyze_yahoo_roster,
                # _analyze_current_matchup, etc.) is hardcoded to Yahoo's API.
                # Say so honestly rather than silently returning only
                # league_info with no explanation, which is what happened
                # before this platform check was fixed (it compared an Enum
                # to a raw string and was always False, so this branch was
                # unreachable for every platform including Yahoo).
                analysis["error"] = (
                    f"Comprehensive analysis (roster, matchups, standings, "
                    f"waiver/trade recommendations) is only implemented for "
                    f"Yahoo leagues today. {league.platform.value.upper()} "
                    f"support is tracked as a follow-up."
                )

            return analysis

        except Exception as e:
            logger.error(f"Error in comprehensive league analysis: {str(e)}")
            return {"error": str(e)}

    def _get_yahoo_token(self, league: UserLeague) -> Optional[str]:
        """Return this league's stored Yahoo access token, or None if the
        league was never connected or the token has expired. Yahoo access
        tokens are short-lived (~1hr), so an expired token is treated the
        same as a missing one -- callers should report a clear "reconnect"
        error rather than let a stale token fail with a cryptic 401 from
        Yahoo's API.
        """
        if not league.yahoo_access_token:
            return None
        if league.yahoo_token_expires_at and league.yahoo_token_expires_at < datetime.utcnow():
            return None
        return league.yahoo_access_token

    async def _analyze_yahoo_roster(self, league: UserLeague) -> Dict[str, Any]:
        """Analyze Yahoo Fantasy roster"""
        try:
            if not league.team_id:
                return {"error": "Team ID not configured"}

            access_token = self._get_yahoo_token(league)
            if not access_token:
                return {"error": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account."}

            # Get roster from Yahoo
            roster_data = await yahoo_service.get_team_roster(access_token, league.team_id)

            if "error" in roster_data:
                return {"error": roster_data["error"]}

            players = roster_data.get("players", [])

            # Real per-league starter requirements, when Yahoo actually
            # exposes them for this league -- see yahoo_service.get_league_settings.
            # Falls back to None (which grade_roster itself turns into a
            # standard 1-QB/2-RB/2-WR/1-TE/1-K/1-DEF lineup) rather than
            # fabricating Yahoo-specific settings that aren't real.
            league_settings = None
            if league.league_key:
                yahoo_settings = await yahoo_service.get_league_settings(access_token, league.league_key)
                if "error" not in yahoo_settings and yahoo_settings.get("starters"):
                    league_settings = {"starters": yahoo_settings["starters"]}

            # Real, deterministic grade from actual roster composition vs
            # actual (or honestly-fallback) starter requirements -- replaces
            # the old pure-LLM-opinion average of per-position AI grades.
            grading_result = roster_grading.grade_roster(players, league_settings)
            position_breakdown = grading_result.get("position_breakdown", {})

            # Analyze each position group
            position_analysis = {}
            roster_strengths = []
            roster_weaknesses = []

            positions = ["QB", "RB", "WR", "TE", "K", "DEF"]

            for position in positions:
                pos_players = [p for p in players if p.get("position") == position]

                if pos_players:
                    # AI-generated summary/strengths/concerns text is still
                    # genuinely useful color -- kept for descriptive text
                    # only, not as the source of truth for the letter grade.
                    pos_analysis = await self._analyze_position_group(
                        position, pos_players, league.league_size, league.scoring_format
                    )
                    position_analysis[position] = pos_analysis

                    # Strength/weakness classification now comes from the
                    # real, deterministic per-position breakdown
                    # (needs_attention/overstocked flags), not the AI's
                    # self-reported letter grade -- the AI summary text is
                    # still included for color.
                    breakdown = position_breakdown.get(position)
                    if breakdown:
                        if breakdown.get("overstocked"):
                            roster_strengths.append(f"{position}: {pos_analysis.get('summary', '')}")
                        elif breakdown.get("needs_attention"):
                            roster_weaknesses.append(f"{position}: {pos_analysis.get('summary', '')}")

            # Get injury concerns
            injury_concerns = await self._check_roster_injuries(players)

            return {
                "total_players": len(players),
                "position_analysis": position_analysis,
                "overall_grade": grading_result.get("grade", "C"),
                "composition_score": grading_result.get("composition_score"),
                "position_breakdown": position_breakdown,
                "strengths": roster_strengths,
                "weaknesses": roster_weaknesses,
                "injury_concerns": injury_concerns,
                "last_updated": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {"error": f"Failed to analyze roster: {str(e)}"}

    async def _analyze_position_group(
        self,
        position: str,
        players: List[Dict],
        league_size: Optional[int] = None,
        scoring_format: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Analyze a specific position group.

        league_size/scoring_format are real per-league settings threaded
        through from _analyze_yahoo_roster's call site, so the AI's
        descriptive text is at least aware of real league context (a 12-team
        PPR league vs. a 10-team standard league). Note: as of this fix,
        this method's returned "grade" is no longer the source of truth for
        the roster's overall grade -- see roster_grading.grade_roster for
        the real, deterministic grade. This method's summary/strengths/
        concerns text is still genuinely useful descriptive color.
        """
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
            league_context = (
                f"{league_size}-team" if league_size else "this"
            ) + f" {scoring_format or 'unknown-scoring'} league"
            analysis_prompt = f"""
            Analyze this {position} group for fantasy football in {league_context}:

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
            access_token = self._get_yahoo_token(league)
            if not access_token:
                return {"error": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account."}

            # Get current week matchups
            current_week = await self._get_current_week()
            matchups = await yahoo_service.get_matchups(access_token, league.league_key, current_week)

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
            access_token = self._get_yahoo_token(league)
            if not access_token:
                return {"error": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account."}

            teams = await yahoo_service.get_league_teams(access_token, league.league_key)

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
            access_token = self._get_yahoo_token(league)
            if not access_token:
                return {"error": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account."}

            # Get trending players
            trending_players = self.player_service.get_trending_players("UP", limit=20)

            # Filter based on league roster needs
            roster_data = await yahoo_service.get_team_roster(access_token, league.team_id)
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
            access_token = self._get_yahoo_token(league)
            if not access_token:
                return {"error": "Your Yahoo connection is missing or has expired. Please reconnect your Yahoo account."}

            # Get user's roster
            roster_data = await yahoo_service.get_team_roster(access_token, league.team_id)
            if "error" in roster_data:
                return {"error": roster_data["error"]}

            # Get league teams for potential trade partners
            teams = await yahoo_service.get_league_teams(access_token, league.league_key)
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

    # Note: get_league_insights, _generate_weekly_outlook,
    # _generate_start_sit_recs, _get_top_pickup_targets, and _optimize_lineup
    # were removed here (dead code, zero callers anywhere in the codebase --
    # the live GET /{league_id}/insights endpoint in leagues.py has its own
    # separate inline implementation and never called these). The removed
    # get_league_insights still contained hardcoded fake picks (e.g.
    # "Lamar Jackson" to start) returned for every league regardless of
    # actual roster, confirming it was stale and not in active use.