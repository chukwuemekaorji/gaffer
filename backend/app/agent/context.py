"""turns dispatched evidence into the prompt context for the generator.

every chunk and stat fact gets a numeric source id (S1, S2, …) so the
generator can produce inline [S3]-style citations. the builder also
returns a `sources` mapping the api will surface to the frontend, so
clicking a citation can jump to the actual source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.agent.dispatcher import DispatchedEvidence


@dataclass
class Source:
    """one citable source the generator can reference by id. covers
    both rag chunks (title + url) and structured facts (e.g. football-
    data.org for a table position)."""

    id: str                 # 'S1', 'S2', ...
    kind: str               # 'chunk', 'stat', 'web'
    title: str
    url: str | None = None
    snippet: str | None = None
    published_at: datetime | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuiltContext:
    sources: list[Source]
    prompt_block: str       # the formatted evidence block we paste into the system prompt


def _format_published(value: datetime | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def build_context(evidence: DispatchedEvidence) -> BuiltContext:
    """walks the evidence bundle and produces a single string block
    plus a sources list. the format is deliberately simple — markdown-
    ish with explicit source ids — because that's what generation
    models cite most reliably."""

    sources: list[Source] = []
    sections: list[str] = []

    next_id = 1

    def add_source(**kw: Any) -> str:
        nonlocal next_id
        sid = f"S{next_id}"
        next_id += 1
        sources.append(Source(id=sid, **kw))
        return sid

    # ---- tactical rag ----
    if evidence.tactical and evidence.tactical.candidates:
        lines = ["## tactical knowledge base"]
        for c in evidence.tactical.candidates:
            sid = add_source(
                kind="chunk",
                title=c.title,
                url=c.url,
                snippet=c.content,
                published_at=c.published_at,
                metadata={
                    "source": c.source,
                    "doc_type": c.doc_type,
                    "era": c.era,
                    "rerank_score": c.rerank_score,
                },
            )
            lines.append(
                f"[{sid}] ({c.source}, {c.doc_type}, era={c.era or 'n/a'}, {_format_published(c.published_at)})\n{c.content}"
            )
        sections.append("\n\n".join(lines))

    # ---- recent rag ----
    if evidence.recent and evidence.recent.candidates:
        lines = ["## recent news and match reports"]
        for c in evidence.recent.candidates:
            sid = add_source(
                kind="chunk",
                title=c.title,
                url=c.url,
                snippet=c.content,
                published_at=c.published_at,
                metadata={
                    "source": c.source,
                    "doc_type": c.doc_type,
                    "era": c.era,
                    "rerank_score": c.rerank_score,
                },
            )
            lines.append(
                f"[{sid}] ({c.source}, {c.doc_type}, {_format_published(c.published_at)})\n{c.content}"
            )
        sections.append("\n\n".join(lines))

    # ---- structured stats ----
    if evidence.stats:
        stat_lines = ["## structured stats (from football-data.org)"]
        s = evidence.stats

        if s.table_position:
            sid = add_source(
                kind="stat",
                title="Premier League table position",
                url="https://www.football-data.org",
                metadata={"kind": "table_position"},
            )
            stat_lines.append(
                f"[{sid}] table position: {s.table_position['position']} "
                f"({s.table_position['played']} played, "
                f"{s.table_position['won']}W {s.table_position['drawn']}D {s.table_position['lost']}L, "
                f"{s.table_position['points']} pts, GD {s.table_position['goal_difference']}, "
                f"form: {s.table_position.get('form') or 'n/a'})"
            )

        if s.next_fixture:
            sid = add_source(
                kind="stat",
                title="Next fixture",
                url="https://www.football-data.org",
                metadata={"kind": "next_fixture"},
            )
            f = s.next_fixture
            stat_lines.append(
                f"[{sid}] next fixture: {f['home_team']} vs {f['away_team']} "
                f"({f['competition']}, kickoff {f['kickoff_utc']})"
            )

        if s.recent_results:
            sid = add_source(
                kind="stat",
                title="Recent results",
                url="https://www.football-data.org",
                metadata={"kind": "recent_results"},
            )
            joined = "; ".join(
                f"{r['home_team']} {r['home_score']}-{r['away_score']} {r['away_team']} ({r['competition']})"
                for r in s.recent_results
            )
            stat_lines.append(f"[{sid}] recent results: {joined}")

        if s.upcoming:
            sid = add_source(
                kind="stat",
                title="Upcoming fixtures",
                url="https://www.football-data.org",
                metadata={"kind": "upcoming"},
            )
            joined = "; ".join(
                f"{f['home_team']} vs {f['away_team']} on {f['kickoff_utc']} ({f['competition']})"
                for f in s.upcoming
            )
            stat_lines.append(f"[{sid}] upcoming fixtures: {joined}")

        if len(stat_lines) > 1:
            sections.append("\n\n".join(stat_lines))

    # ---- web search ----
    if evidence.web and evidence.web.snippets:
        lines = ["## web search results (last resort grounding)"]
        for snip in evidence.web.snippets[:5]:        # cap to avoid context bloat
            sid = add_source(
                kind="web",
                title=snip.title,
                url=snip.url,
                published_at=snip.published_at,
            )
            lines.append(f"[{sid}] {snip.title} — {snip.url}")
        sections.append("\n\n".join(lines))

    prompt_block = "\n\n".join(sections) if sections else "(no evidence retrieved)"
    return BuiltContext(sources=sources, prompt_block=prompt_block)