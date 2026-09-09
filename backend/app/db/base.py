from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# pool_pre_ping: Supabase / pgbouncer silently drops idle server connections,
# which otherwise surfaces as a random error on the first query after an idle
# gap (seen as intermittent 503s when the frontend fires two calls in quick
# succession). pool_pre_ping checks the connection is alive before handing it
# out; pool_recycle proactively retires connections older than 5 min.
# Pool kept deliberately small: the Supabase session pooler has a modest
# connection cap on the free tier, and a single Render web instance doesn't
# need much concurrency. 3 + 2 overflow = 5 max connections per instance.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=3,
    max_overflow=2,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()