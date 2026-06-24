"""fastapi entrypoint. routes get mounted from app/api/ as we add them."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import retrieve as retrieve_api
from app.api import route as route_api
from app.api import stats as stats_api
from app.config import get_settings
from app.db.session import get_db

settings = get_settings()

app = FastAPI(
    title="Gaffer API",
    description="grounded football tactical analyst for manchester united",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(retrieve_api.router)
app.include_router(stats_api.router)
app.include_router(route_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, object]:
    db_version = db.execute(text("select version()")).scalar_one()
    has_vector = db.execute(
        text("select exists(select 1 from pg_extension where extname = 'vector')")
    ).scalar_one()
    return {
        "status": "ok",
        "postgres_version": db_version,
        "pgvector_enabled": bool(has_vector),
    }