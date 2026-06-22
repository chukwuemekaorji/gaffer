"""sqlalchemy session setup. we use the engine directly for raw sql
(retrieval queries are too custom for the orm to help) and sessions
only for the few places we want orm convenience."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# pool_pre_ping=true catches stale connections that supabase's pooler
# sometimes closes on us. small overhead, big reliability win
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """fastapi dependency. yields a session and makes sure it's closed
    even if the route raises."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()