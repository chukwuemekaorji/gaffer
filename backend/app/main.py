"""fastapi entrypoint. routes get mounted from app/api/ as we add them."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

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
    # cheap liveness check. expand later to actually verify db + redis are reachable
    return {"status": "ok", "env": settings.app_env}