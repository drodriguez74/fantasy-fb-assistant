from espn_api.football import League
from typing import Dict, List, Optional, Any, Union
import asyncio
from datetime import datetime
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def async_wrapper(func):
    """Wrapper to run synchronous espn-api methods in async context"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        # Use functools.partial to properly handle keyword arguments
        from functools import partial
        bound_func = partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, bound_func)
    return wrapper

class ESPNFantasyServiceEnhanced:
    def __init__(self):
        self._leagues = {}  # Cache for league objects

    def _get_league(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> League:
        """Get or create ESPN League object with optional authentication"""
        # Cache key includes whether this call is authenticated (not the
        # cookie values themselves) so a public-only lookup for a league_id
        # never gets served back to a caller that passed real per-user
        # swid/espn_s2 for that same league_id, and vice versa.
        cache_key = f"{league_id}_{season}_{'auth' if (swid and espn_s2) else 'public'}"
        
        if cache_key not in self._leagues:
            try:
                # Validate league_id
                if not league_id:
                    raise ValueError("League ID cannot be empty")
                
                league_id_int = int(league_id)
                logger.info(f"Attempting to connect to ESPN league {league_id_int} for season {season}")
                
                # Try different seasons if the requested one fails
                seasons_to_try = [season]
                if season == 2025:
                    seasons_to_try = [2025, 2024]  # Try 2025 first, fallback to 2024 if needed
                elif season == 2024:
                    seasons_to_try = [2024, 2023]  # Try 2023 as fallback
                
                league_obj = None
                last_error = None
                
                for try_season in seasons_to_try:
                    try:
                        logger.info(f"Trying season {try_season} for league {league_id_int}")
                        
                        # For public leagues (no authentication needed)
                        if not swid or not espn_s2:
                            try:
                                league_obj = League(
                                    league_id=league_id_int, 
                                    year=try_season
                                )
                            except Exception as public_error:
                                # Check if this is the specific private league error
                                if "'NoneType' object has no attribute 'get'" in str(public_error):
                                    raise ValueError(f"League {league_id_int} is private and requires authentication. Please provide SWID and espn_s2 cookies from your ESPN account.")
                                else:
                                    raise public_error
                        else:
                            # For private leagues (authentication required)
                            league_obj = League(
                                league_id=league_id_int, 
                                year=try_season,
                                swid=swid,
                                espn_s2=espn_s2
                            )
                        
                        # Validate the created league object
                        if not league_obj:
                            logger.error(f"ESPN API returned None for league object (season {try_season})")
                            continue
                        
                        # Test basic access to ensure the league is valid
                        try:
                            test_id = getattr(league_obj, 'league_id', None)
                            test_year = getattr(league_obj, 'year', None)
                            test_settings = getattr(league_obj, 'settings', None)
                            
                            logger.info(f"League object created - ID: {test_id}, Year: {test_year}, Settings: {test_settings is not None}")
                            
                            if test_id and test_year:
                                logger.info(f"Successfully connected to ESPN league {test_id} for season {test_year}")
                                self._leagues[cache_key] = league_obj
                                return league_obj
                            else:
                                logger.error(f"League validation failed - missing basic attributes (season {try_season})")
                                continue
                        except Exception as validation_error:
                            logger.error(f"League validation failed for season {try_season}: {str(validation_error)}")
                            last_error = validation_error
                            continue
                            
                    except Exception as season_error:
                        logger.error(f"Failed to create league object for season {try_season}: {str(season_error)}")
                        last_error = season_error
                        continue
                
                # If we get here, all seasons failed
                if last_error:
                    raise ValueError(f"ESPN API error after trying multiple seasons: {str(last_error)}")
                else:
                    raise ValueError("ESPN API returned None for league object across all attempted seasons")
                
            except ValueError as ve:
                logger.error(f"Invalid league parameters: {str(ve)}")
                raise
            except Exception as e:
                # Common ESPN API errors
                error_msg = str(e).lower()
                if "league_id" in error_msg or "invalid" in error_msg:
                    logger.error(f"Invalid ESPN league ID {league_id}: {str(e)}")
                    raise ValueError(f"Invalid ESPN league ID: {league_id}. The league might not exist or might be from a different season.")
                elif "private" in error_msg or "access" in error_msg or "permission" in error_msg:
                    logger.error(f"ESPN league {league_id} requires authentication: {str(e)}")
                    raise ValueError(f"League {league_id} is private and requires authentication (SWID and espn_s2 cookies)")
                else:
                    logger.error(f"Failed to create ESPN League object: {str(e)}")
                    raise ValueError(f"ESPN API error: {str(e)}")
        
        return self._leagues[cache_key]

    @async_wrapper
    def get_league_info(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> Dict[str, Any]:
        """Get comprehensive ESPN league information"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Validate league object
            if not league:
                return {"error": "Failed to create league connection - league object is None"}
            
            # Check if league has required attributes
            if not hasattr(league, 'league_id'):
                return {"error": "Invalid league - league ID not found"}
            
            settings = getattr(league, 'settings', None)
            teams = getattr(league, 'teams', [])
            
            return {
                "league_id": league.league_id,
                "league_name": getattr(settings, 'name', 'ESPN League') if settings else 'ESPN League',
                "season": league.year if hasattr(league, 'year') else season,
                "current_week": getattr(league, 'current_week', 1),
                "scoring_type": getattr(settings, 'scoring_type', 'STANDARD') if settings else 'STANDARD',
                "team_count": len(teams) if teams else 0,
                "roster_settings": {
                    "roster_size": getattr(settings, 'roster_size', 16) if settings else 16,
                    "starting_lineup_size": getattr(settings, 'starting_lineup_size', 9) if settings else 9,
                },
                "draft_settings": {
                    "draft_type": getattr(settings, 'draft_type', 'SNAKE') if settings else 'SNAKE',
                    "draft_date": getattr(settings, 'draft_date', None) if settings else None,
                    "draft_completed": hasattr(league, 'draft') and league.draft is not None and len(getattr(league, 'draft', [])) > 0
                },
                "playoff_settings": {
                    "playoff_teams": getattr(settings, 'playoff_team_count', 6) if settings else 6,
                    "playoff_start_week": getattr(settings, 'playoff_start_week', 15) if settings else 15
                }
            }
        except Exception as e:
            logger.error(f"Error getting league info: {str(e)}")
            return {"error": f"Failed to get league info: {str(e)}"}

    @async_wrapper
    def get_league_teams(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Get all teams in the ESPN league"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            teams_data = []
            for team in league.teams:
                teams_data.append({
                    "team_id": team.team_id,
                    "team_name": f"{team.team_name}",
                    "owner": getattr(team, 'owner', 'Unknown Owner'),
                    "wins": team.wins,
                    "losses": team.losses,
                    "ties": getattr(team, 'ties', 0),
                    "points_for": team.points_for,
                    "points_against": team.points_against,
                    "acquisition_budget": getattr(team, 'acquisition_budget', 100),
                    "acquisitions": getattr(team, 'acquisitions', 0),
                    "trades": getattr(team, 'trades', 0),
                    "standing": getattr(team, 'standing', 0),
                    "playoff_pct": getattr(team, 'playoff_pct', 0.0),
                    "roster": self._format_roster(team.roster) if hasattr(team, 'roster') else []
                })
            
            return teams_data
        except Exception as e:
            logger.error(f"Error getting teams: {str(e)}")
            return [{"error": f"Failed to get teams: {str(e)}"}]

    @async_wrapper
    def get_team_roster(self, league_id: Union[str, int], team_id: int, season: int = 2024, week: int = None, swid: str = None, espn_s2: str = None) -> Dict[str, Any]:
        """Get roster for a specific team"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Find the specific team
            target_team = None
            for team in league.teams:
                if team.team_id == team_id:
                    target_team = team
                    break
            
            if not target_team:
                return {"error": f"Team {team_id} not found in league"}
            
            # Get roster for specific week if provided
            if week:
                roster = target_team.roster(week=week)
            else:
                roster = target_team.roster
            
            return {
                "team_id": target_team.team_id,
                "team_name": target_team.team_name,
                "owner": getattr(target_team, 'owner', 'Unknown Owner'),
                "roster_size": len(roster),
                "players": self._format_roster(roster),
                "week": week or league.current_week
            }
        except Exception as e:
            logger.error(f"Error getting team roster: {str(e)}")
            return {"error": f"Failed to get team roster: {str(e)}"}

    @async_wrapper 
    def get_available_players(self, league_id: Union[str, int], season: int = 2024, position: str = None, size: int = 50, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Get available players (free agents/waivers)"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Get free agents
            position_filter = None
            if position:
                position_map = {
                    'QB': 1, 'RB': 2, 'WR': 3, 'TE': 4, 'K': 5, 'DEF': 16
                }
                position_filter = position_map.get(position.upper())
            
            available_players = league.free_agents(size=size, position=position_filter)
            
            return [self._format_player(player) for player in available_players]
        except Exception as e:
            logger.error(f"Error getting available players: {str(e)}")
            return [{"error": f"Failed to get available players: {str(e)}"}]

    @async_wrapper
    def get_draft_info(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> Dict[str, Any]:
        """Get draft information and results"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)

            # _get_league caches League objects per (league_id, season, auth)
            # for the life of this process, and espn_api only populates
            # league.draft once, at construction time. Without an explicit
            # refresh here, a live-draft session polling this method every
            # ~10s (see draft_assistant_service._get_espn_draft_state) would
            # see the exact same picks forever instead of real ones as they
            # happen. refresh_draft() re-fetches picks from ESPN's live API
            # -- but espn_api's _fetch_draft() *appends* to league.draft
            # rather than replacing it, so repeated refreshes on the same
            # cached League object would otherwise duplicate every prior
            # pick each time (verified against a real drafted league: pick
            # count doubled on the second call). Reset the list first so
            # each refresh reflects only the current real picks.
            league.draft = []
            league.refresh_draft()

            # espn_api's Pick objects (espn_api.base_pick.BasePick) expose
            # team/playerId/playerName/round_num/round_pick/keeper_status --
            # there is no pick_number, player_name, player_id, position, or
            # keeper attribute, so the original field names below (carried
            # over from an earlier/different version of the library) raised
            # AttributeError on every real league that had actually drafted.
            # league.draft is already returned by ESPN in overall draft
            # order, so the 1-based enumerate index is the real overall pick
            # number (not fabricated -- it's ESPN's own ordering).
            draft_picks = []
            if hasattr(league, 'draft') and league.draft:
                for i, pick in enumerate(league.draft, start=1):
                    draft_picks.append({
                        "pick_number": i,
                        "round": pick.round_num,
                        "team_id": pick.team.team_id if pick.team else None,
                        "team_name": pick.team.team_name if pick.team else None,
                        "player_name": pick.playerName,
                        "player_id": pick.playerId,
                        # BasePick doesn't carry position data at all; leaving
                        # this as an honest "unknown" rather than guessing.
                        "position": "UNKNOWN",
                        "keeper": bool(pick.keeper_status)
                    })
            
            return {
                "draft_completed": len(draft_picks) > 0,
                "total_picks": len(draft_picks),
                "rounds": max([pick["round"] for pick in draft_picks]) if draft_picks else 0,
                "draft_order": self._get_draft_order(league),
                "picks": draft_picks
            }
        except Exception as e:
            logger.error(f"Error getting draft info: {str(e)}")
            return {"error": f"Failed to get draft info: {str(e)}"}

    @async_wrapper
    def get_matchups(self, league_id: Union[str, int], week: int, season: int = 2024, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Get matchups for a specific week"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Get scoreboard for the week
            scoreboard = league.scoreboard(week=week)
            
            matchups = []
            for matchup in scoreboard:
                matchups.append({
                    "week": week,
                    "home_team": {
                        "team_id": matchup.home_team.team_id,
                        "team_name": matchup.home_team.team_name,
                        "owner": getattr(matchup.home_team, 'owner', 'Unknown Owner'),
                        "score": matchup.home_score,
                        "projected_score": getattr(matchup, 'home_projected', 0.0)
                    },
                    "away_team": {
                        "team_id": matchup.away_team.team_id,
                        "team_name": matchup.away_team.team_name, 
                        "owner": getattr(matchup.away_team, 'owner', 'Unknown Owner'),
                        "score": matchup.away_score,
                        "projected_score": getattr(matchup, 'away_projected', 0.0)
                    },
                    "winner": self._determine_winner(matchup)
                })
            
            return matchups
        except Exception as e:
            logger.error(f"Error getting matchups: {str(e)}")
            return [{"error": f"Failed to get matchups: {str(e)}"}]

    @async_wrapper
    def get_standings(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Get league standings"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            standings = []
            for team in league.teams:
                standings.append({
                    "team_id": team.team_id,
                    "team_name": team.team_name,
                    "owner": getattr(team, 'owner', 'Unknown Owner'),
                    "wins": team.wins,
                    "losses": team.losses,
                    "ties": getattr(team, 'ties', 0),
                    "points_for": team.points_for,
                    "points_against": team.points_against,
                    "win_percentage": team.wins / (team.wins + team.losses) if (team.wins + team.losses) > 0 else 0,
                    "points_per_game": team.points_for / (team.wins + team.losses) if (team.wins + team.losses) > 0 else 0,
                    "standing": getattr(team, 'standing', 0),
                    "playoff_pct": getattr(team, 'playoff_pct', 0.0)
                })
            
            # Sort by wins, then by points for
            standings.sort(key=lambda x: (-x["wins"], -x["points_for"]))
            
            # Add rank
            for i, team in enumerate(standings):
                team["rank"] = i + 1
            
            return standings
        except Exception as e:
            logger.error(f"Error getting standings: {str(e)}")
            return [{"error": f"Failed to get standings: {str(e)}"}]

    @async_wrapper
    def get_power_rankings(self, league_id: Union[str, int], week: int = None, season: int = 2024, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Get ESPN power rankings for the league"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Use current week if not specified
            if not week:
                week = league.current_week
            
            power_rankings = league.power_rankings(week=week)
            
            rankings = []
            for rank, (power_score, team) in enumerate(power_rankings, 1):
                rankings.append({
                    "rank": rank,
                    "team_id": team.team_id,
                    "team_name": team.team_name,
                    "owner": getattr(team, 'owner', 'Unknown Owner'),
                    "power_score": power_score,
                    "wins": team.wins,
                    "losses": team.losses,
                    "points_for": team.points_for,
                    "points_against": team.points_against
                })
            
            return rankings
        except Exception as e:
            logger.error(f"Error getting power rankings: {str(e)}")
            return [{"error": f"Failed to get power rankings: {str(e)}"}]

    @async_wrapper
    def search_players(self, league_id: Union[str, int], name: str, season: int = 2024, swid: str = None, espn_s2: str = None) -> List[Dict[str, Any]]:
        """Search for players by name"""
        try:
            league = self._get_league(league_id, season, swid, espn_s2)
            
            # Get all available players and filter by name
            all_players = league.free_agents(size=200)
            
            # Simple name matching
            matching_players = []
            search_term = name.lower()
            
            for player in all_players:
                player_name = getattr(player, 'name', '').lower()
                if search_term in player_name:
                    matching_players.append(self._format_player(player))
            
            return matching_players[:20]  # Limit to 20 results
        except Exception as e:
            logger.error(f"Error searching players: {str(e)}")
            return [{"error": f"Failed to search players: {str(e)}"}]

    def _format_player(self, player) -> Dict[str, Any]:
        """Format a player object into a standardized dictionary"""
        try:
            return {
                "player_id": getattr(player, 'playerId', None),
                "name": getattr(player, 'name', 'Unknown Player'),
                "position": getattr(player, 'position', 'UNKNOWN'),
                "team": getattr(player, 'proTeam', 'FA'),
                "injury_status": getattr(player, 'injuryStatus', 'ACTIVE'),
                "projected_points": getattr(player, 'projected_points', 0.0),
                "total_points": getattr(player, 'total_points', 0.0),
                "avg_points": getattr(player, 'avg_points', 0.0),
                "percent_owned": getattr(player, 'percent_owned', 0.0),
                "percent_started": getattr(player, 'percent_started', 0.0),
                "acquisition_type": getattr(player, 'acquisition_type', 'ADD'),
                "eligibile_slots": getattr(player, 'eligibleSlots', []),
                "stats": self._extract_player_stats(player)
            }
        except Exception as e:
            logger.error(f"Error formatting player: {str(e)}")
            return {"error": f"Failed to format player: {str(e)}"}

    def _format_roster(self, roster) -> List[Dict[str, Any]]:
        """Format a roster into a list of player dictionaries"""
        try:
            formatted_roster = []
            for player in roster:
                player_data = self._format_player(player)
                player_data["lineup_slot"] = getattr(player, 'lineupSlot', None)
                player_data["slot_position"] = getattr(player, 'slot_position', 'BENCH')
                formatted_roster.append(player_data)
            return formatted_roster
        except Exception as e:
            logger.error(f"Error formatting roster: {str(e)}")
            return []

    def _extract_player_stats(self, player) -> Dict[str, Any]:
        """Extract player statistics"""
        try:
            stats = {}
            
            # Try to get stats from different possible attributes
            if hasattr(player, 'stats'):
                stats.update(getattr(player, 'stats', {}))
            
            # Add commonly available stats
            stats.update({
                "projected_points": getattr(player, 'projected_points', 0.0),
                "total_points": getattr(player, 'total_points', 0.0),
                "avg_points": getattr(player, 'avg_points', 0.0)
            })
            
            return stats
        except:
            return {}

    def _get_draft_order(self, league) -> List[int]:
        """Extract draft order from league"""
        try:
            if hasattr(league, 'draft') and league.draft:
                # Get first round picks to determine draft order. BasePick
                # has no pick_number attribute (see get_draft_info); the
                # within-round pick order is round_pick.
                first_round = [pick for pick in league.draft if pick.round_num == 1]
                first_round.sort(key=lambda x: x.round_pick)
                return [pick.team.team_id for pick in first_round if pick.team]
            return []
        except:
            return []

    def _determine_winner(self, matchup) -> Optional[str]:
        """Determine the winner of a matchup"""
        try:
            if matchup.home_score > matchup.away_score:
                return "home"
            elif matchup.away_score > matchup.home_score:
                return "away"
            else:
                return "tie"
        except:
            return None

    async def connect_league(self, league_id: Union[str, int], season: int = 2024, swid: str = None, espn_s2: str = None) -> Dict[str, Any]:
        """Test connection to an ESPN league and return basic info"""
        try:
            league_info = await self.get_league_info(league_id, season, swid, espn_s2)
            
            if "error" in league_info:
                return {"error": league_info["error"], "connected": False}
            
            return {
                "connected": True,
                "league_info": league_info,
                "requires_auth": False,  # Will be updated based on access level
                "access_level": "full" if swid and espn_s2 else "public"
            }
        except Exception as e:
            logger.error(f"Error connecting to ESPN league: {str(e)}")
            return {"error": str(e), "connected": False}

    async def test_known_league(self) -> Dict[str, Any]:
        """Test connection with a known working ESPN league for diagnostics"""
        # Using a known public ESPN league for testing
        test_league_id = 252353  # This is a verified working league from our test
        try:
            logger.info(f"Testing ESPN API with known league ID {test_league_id}")
            result = await self.connect_league(test_league_id, 2024)
            return {
                "test_league_id": test_league_id,
                "test_result": result,
                "api_status": "working" if result.get("connected") else "not_working"
            }
        except Exception as e:
            logger.error(f"Known league test failed: {str(e)}")
            return {
                "test_league_id": test_league_id,
                "test_result": {"error": str(e), "connected": False},
                "api_status": "error"
            }

# Create service instance
espn_service_enhanced = ESPNFantasyServiceEnhanced()