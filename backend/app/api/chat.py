"""the chat endpoint. two routes: a blocking one (handy for tests
and curl) and a streaming server-sent-events one (what the frontend
talks to)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.orchestrator import answer, answer_stream
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["agent"])


class ChatRequest(BaseModel):
    query: str


@router.post("")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    response = await answer(db, req.query)
    return {
        "answer": response.answer,
        "decision": {
            "routes": [r.value for r in response.decision.routes],
            "reasoning": response.decision.reasoning,
        },
        "sources": [
            {
                "id": s.id,
                "kind": s.kind,
                "title": s.title,
                "url": s.url,
            }
            for s in response.sources
        ],
        "latency_ms": response.latency_ms,
    }


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    """server-sent events. each event is a json blob describing one
    step of the agent loop. frontend consumes this with EventSource
    or fetch + ReadableStream."""

    async def event_stream():
        async for event in answer_stream(db, req.query):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )