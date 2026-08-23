import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated, Optional


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

    # Outbound email (SMTP) for real verification/password-reset delivery --
    # see email_service.py. Optional like the API keys above: when
    # SMTP_SERVER and SMTP_USERNAME are both unset, EmailService stays in
    # its honest dev-log mode (logs the email instead of sending, still
    # returns True) rather than crashing. Set all of SMTP_SERVER/
    # SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD/FROM_EMAIL together to enable
    # real sending.
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: Optional[str] = None

    # Origins allowed to call this API with credentials. Defaults to the
    # frontend's local dev URLs (matches vite.config.ts's non-default port
    # and its 127.0.0.1 equivalent, plus the backend's own two forms) so
    # local dev needs zero config. In production, set this to the real
    # deployed frontend URL(s) -- a bare "*" is invalid here per the CORS
    # spec once allow_credentials=True is set below, so this is never a
    # wildcard. Accepts either a comma-separated string (easiest to hand-type
    # in a .env, e.g. "https://foo.vercel.app,https://bar.com") or a JSON
    # array string (pydantic-settings' default list[str] parsing).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, v):
        # NoDecode means we always receive the raw env string here (never
        # pydantic-settings' own JSON auto-decode) -- handle both a JSON
        # array and a plain comma-separated list ourselves.
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return v

    # extra="ignore": this app's real per-user ESPN/Yahoo credentials are
    # stored in the database (UserLeague rows), not here -- but a .env can
    # reasonably carry extra developer-local values (e.g. for manual
    # verification scripts) without crashing the entire app on import, which
    # is what pydantic-settings' default extra="forbid" does.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()