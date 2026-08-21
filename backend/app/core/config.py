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
    
    CORS_ORIGINS: list[str] = ["*"]  # Allow all origins for development

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()