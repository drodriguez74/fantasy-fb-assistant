from fastapi import APIRouter
from app.api.v1.endpoints import players, blog, auth, users, leagues, content, historical, analytics, waiver_wire, advanced_analysis, game_situations, post_draft, league_scoring, matchup_analysis, trade, notifications

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(players.router, prefix="/players", tags=["players"])
api_router.include_router(blog.router, prefix="/blog", tags=["blog"])
api_router.include_router(leagues.router, prefix="/leagues", tags=["leagues"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(historical.router, prefix="/historical", tags=["historical"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(waiver_wire.router, prefix="/waiver-wire", tags=["waiver-wire"])
api_router.include_router(advanced_analysis.router, prefix="/advanced-analysis", tags=["advanced-analysis"])
api_router.include_router(game_situations.router, prefix="/game-situations", tags=["game-situations"])
api_router.include_router(post_draft.router, prefix="/post-draft", tags=["post-draft"])
api_router.include_router(league_scoring.router, prefix="/league-scoring", tags=["league-scoring"])
api_router.include_router(matchup_analysis.router, prefix="/matchup-analysis", tags=["matchup-analysis"])
api_router.include_router(trade.router, prefix="/trade", tags=["trade"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])