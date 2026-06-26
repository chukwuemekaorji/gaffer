"""the chat endpoint. two routes: a blocking one (handy for tests
and curl) and a streaming server-sent-events one (what the frontend
talks to).

the request body carries an optional 'history' field — prior turns
of the conversation. we pass them through so the agent can reason in
context."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.orchestrator import answer, answer_stream
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["agent"])


class ChatTurn(BaseModel):
    """a single turn in the conversation, sent by the frontend so the
    backend can reason with context. role is 'user' or 'assistant'."""
    role: str
    text: str


class ChatRequest(BaseModel):
    query: str
    # optional history of prior turns. the orchestrator caps the
    # window internally (last 8 turns) so we don't have to pre-trim
    # here — let the api accept whatever the frontend sends and the
    # agent decide how much to use.
    history: list[ChatTurn] = []


def _history_pairs(req: ChatRequest) -> list[tuple[str, str]]:
    """convert pydantic turns into the (role, text) tuples the
    orchestrator and downstream functions expect. keeping this as a
    helper means if we add more fields to ChatTurn later (timestamps,
    sources, etc) the orchestrator's signature doesn't have to change."""
    return [(t.role, t.text) for t in req.history]


@router.post("")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    response = await answer(db, req.query, history=_history_pairs(req))
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
    history = _history_pairs(req)

    async def event_stream():
        async for event in answer_stream(db, req.query, history=history):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )