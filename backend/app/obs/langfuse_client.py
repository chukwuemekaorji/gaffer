"""langfuse client wrapper.

langfuse traces every agent run as a single trace, with nested spans
for each stage (route, dispatch, generate). on the frontend (their ui)
you can drill into any past query and see exactly what evidence the
generator received and what it produced.

we wrap their client so the rest of the codebase doesn't import langfuse
directly — easier to swap or stub for tests."""

from __future__ import annotations

import logging
from typing import Any

from langfuse import Langfuse

from app.config import get_settings

log = logging.getLogger(__name__)


_client: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    """returns a singleton client. if langfuse env isn't configured we
    return None and callers no-op — observability should never break
    the request path."""
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        log.debug("langfuse not configured, observability disabled")
        return None

    try:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return _client
    except Exception as exc:
        log.warning("langfuse init failed: %s", exc)
        return None


def safe_trace_event(name: str, **attributes: Any) -> None:
    """convenience for emitting a one-off event when we don't have a
    span context handy. swallows all failures — observability never
    breaks the request path."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.event(name=name, metadata=attributes)
    except Exception as exc:
        log.warning("langfuse event failed: %s", exc)