"""fastapi entrypoint. routes get mounted from app/api/ as we add them."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db

settings = get_settings()

app = FastAPI(
    title="Gaffer API",
    description="grounded football tactical analyst for manchester united",
    version="0.1.0",
)

# next.js dev server runs on 3000, prod frontend gets added once deployed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    # cheap liveness check. just confirms the api process is up.
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, object]:
    """confirms we can reach postgres and pgvector is installed.
    if either fails this 500s, which is what we want for a health probe."""
    db_version = db.execute(text("select version()")).scalar_one()
    has_vector = db.execute(
        text("select exists(select 1 from pg_extension where extname = 'vector')")
    ).scalar_one()
    return {
        "status": "ok",
        "postgres_version": db_version,
        "pgvector_enabled": bool(has_vector),
    }