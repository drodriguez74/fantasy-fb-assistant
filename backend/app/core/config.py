from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Fantasy Football Assistant"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"
    
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    ESPN_CLIENT_ID: Optional[str] = None
    ESPN_CLIENT_SECRET: Optional[str] = None
    
    YAHOO_CLIENT_ID: Optional[str] = None
    YAHOO_CLIENT_SECRET: Optional[str] = None
    
    SLEEPER_API_URL: str = "https://api.sleeper.app/v1"

    # FantasyPros' real public Consensus Rankings/ADP API (see
    # fantasypros_service.py for the endpoint/auth details) -- third
    # consensus-ranking source alongside Sleeper search_rank and ESPN
    # percent_owned. Optional like OPENAI_API_KEY/ANTHROPIC_API_KEY above:
    # absent means ConsensusRankingService degrades to its existing
    # Sleeper/ESPN-only behavior, not a crash.
    FANTASYPROS_API_KEY: Optional[str] = None

    CORS_ORIGINS: list[str] = ["*"]  # Allow all origins for development

    # extra="ignore": this app's real per-user ESPN/Yahoo credentials are
    # stored in the database (UserLeague rows), not here -- but a .env can
    # reasonably carry extra developer-local values (e.g. for manual
    # verification scripts) without crashing the entire app on import, which
    # is what pydantic-settings' default extra="forbid" does.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()