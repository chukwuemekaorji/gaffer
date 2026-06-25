"""stratified eval set covering the routes the agent supports.

each entry carries:
  - id: stable identifier for cross-config comparison
  - category: route type, used for stratified analysis
  - query: the actual user question
  - expected_routes: at least one must match what the router picks
  - expected_source_kinds: the agent's answer should cite at least
    one source of each listed kind (e.g. ['chunk'] for rag-only,
    ['stat'] for stats-only, ['chunk', 'stat'] for multi-route)
  - reference: human-written notes on what a correct answer covers.
    used by the faithfulness judge — not a verbatim string match.
  - allow_refuse: when true, refusal is an acceptable answer (used
    for genuinely off-topic queries)

the set deliberately isn't huge. 40 queries is enough to surface
configuration deltas in aggregate; bigger sets cost more api spend
without much new signal. when we want statistical confidence we'll
bootstrap-sample the existing set."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalQuery:
    id: str
    category: str
    query: str
    expected_routes: list[str]
    expected_source_kinds: list[str] = field(default_factory=list)
    reference: str = ""
    allow_refuse: bool = False


DATASET: list[EvalQuery] = [
    # ----- tactical analysis (rag-only) -----
    EvalQuery(
        id="tac-001",
        category="tactical",
        query="how does Carrick set up against teams that defend deep",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="should describe build-up structure, midfield rotations, wide overloads or movement that breaks low blocks; cite tactical articles",
    ),
    EvalQuery(
        id="tac-002",
        category="tactical",
        query="explain Amorim's 3-4-3 pressing scheme",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="should cover triggers for the press, wing-back roles, vertical compactness, transition into the half-spaces",
    ),
    EvalQuery(
        id="tac-003",
        category="tactical",
        query="what role does Casemiro play under Carrick",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="defensive midfield anchor in the double pivot, screens centre-backs, allows mainoo more progressive freedom",
    ),
    EvalQuery(
        id="tac-004",
        category="tactical",
        query="how do United build out from the back",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="should describe goalkeeper involvement, centre-back splits, double pivot dropping in, fullback positioning",
    ),
    EvalQuery(
        id="tac-005",
        category="tactical",
        query="what's a back three and when is it useful",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="general tactical concept; even without much corpus the agent should explain or refuse cleanly",
    ),
    EvalQuery(
        id="tac-006",
        category="tactical",
        query="how does Mainoo create chances",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="should describe progressive carries, line-breaking passes, third-man combinations, half-space involvement",
    ),

    # ----- live facts (stats-only) -----
    EvalQuery(
        id="stat-001",
        category="stats",
        query="where are we in the table",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="must cite football-data.org for the position; should mention played, points, goal difference",
    ),
    EvalQuery(
        id="stat-002",
        category="stats",
        query="when is our next match",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="next fixture from the cache: opponent, competition, kickoff time",
    ),
    EvalQuery(
        id="stat-003",
        category="stats",
        query="what are our last 5 results",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="recent_results array; each item should be scoreline + competition",
    ),
    EvalQuery(
        id="stat-004",
        category="stats",
        query="how many points have we got in the league",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="table_position.points",
    ),
    EvalQuery(
        id="stat-005",
        category="stats",
        query="what's our goal difference this season",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="table_position.goal_difference",
    ),
    EvalQuery(
        id="stat-006",
        category="stats",
        query="have we played in the champions league this season",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="should be answerable from recent_results + competition codes",
    ),
    EvalQuery(
        id="stat-007",
        category="stats",
        query="when do we play next at old trafford",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="upcoming home fixture lookup",
    ),
    EvalQuery(
        id="stat-008",
        category="stats",
        query="who do we play this weekend",
        expected_routes=["stats"],
        expected_source_kinds=["stat"],
        reference="upcoming fixtures filtered to current week",
    ),

    # ----- recent events (recent_rag, possibly + stats) -----
    EvalQuery(
        id="recent-001",
        category="recent",
        query="how did Mainoo play in our last match",
        expected_routes=["recent_rag"],
        expected_source_kinds=["chunk"],
        reference="must cite a match report; should describe his actual contribution from the report",
    ),
    EvalQuery(
        id="recent-002",
        category="recent",
        query="what happened in our last game",
        expected_routes=["recent_rag", "stats"],
        expected_source_kinds=["chunk"],
        reference="match report or recent result; cite either",
    ),
    EvalQuery(
        id="recent-003",
        category="recent",
        query="any transfer news this week",
        expected_routes=["recent_rag", "web_search"],
        expected_source_kinds=["chunk", "web"],
        reference="news ingestion or web search; date-bounded",
    ),
    EvalQuery(
        id="recent-004",
        category="recent",
        query="how did we lose to chelsea recently",
        expected_routes=["recent_rag"],
        expected_source_kinds=["chunk"],
        reference="if there's no chelsea report in the corpus, the agent should say so cleanly",
    ),
    EvalQuery(
        id="recent-005",
        category="recent",
        query="any injuries i should know about",
        expected_routes=["recent_rag", "web_search"],
        expected_source_kinds=["chunk", "web"],
        reference="news or web; if nothing concrete, should say so",
    ),
    EvalQuery(
        id="recent-006",
        category="recent",
        query="who scored in our last win",
        expected_routes=["recent_rag", "stats"],
        expected_source_kinds=["chunk", "stat"],
        reference="recent results + match report cross-reference",
    ),

    # ----- comparison / synthesis (multi-route) -----
    EvalQuery(
        id="comp-001",
        category="comparison",
        query="compare Bruno's role under Ten Hag and Carrick",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="should contrast positions, freedom, defensive duties, output; cite chunks tagged with different eras",
    ),
    EvalQuery(
        id="comp-002",
        category="comparison",
        query="how does Carrick's pressing differ from Amorim's",
        expected_routes=["tactical_rag"],
        expected_source_kinds=["chunk"],
        reference="height of the press, triggers, shape, risk profile",
    ),
    EvalQuery(
        id="comp-003",
        category="comparison",
        query="what's changed since Amorim left",
        expected_routes=["tactical_rag", "recent_rag"],
        expected_source_kinds=["chunk"],
        reference="shift from 3-4-3 to 4-2-3-1, results trajectory; mix of tactical analysis and recent reports",
    ),
    EvalQuery(
        id="comp-004",
        category="comparison",
        query="how do we play differently away from home this season",
        expected_routes=["tactical_rag", "stats"],
        expected_source_kinds=["chunk", "stat"],
        reference="tactical adjustments + actual away record",
    ),

    # ----- ambiguous / interesting routing edge cases -----
    EvalQuery(
        id="amb-001",
        category="ambiguous",
        query="how are we doing",
        expected_routes=["stats", "recent_rag"],
        expected_source_kinds=["stat"],
        reference="open question — should default to current form: table position + last few results",
    ),
    EvalQuery(
        id="amb-002",
        category="ambiguous",
        query="thoughts on the squad right now",
        expected_routes=["tactical_rag", "recent_rag"],
        expected_source_kinds=["chunk"],
        reference="should pull recent analysis; opinion-shaped but grounded",
    ),
    EvalQuery(
        id="amb-003",
        category="ambiguous",
        query="how did we play",
        expected_routes=["recent_rag"],
        expected_source_kinds=["chunk"],
        reference="pronoun-only reference to last match; agent can clarify which match if ambiguous",
    ),
    EvalQuery(
        id="amb-004",
        category="ambiguous",
        query="what do we need to win the league",
        expected_routes=["tactical_rag", "stats"],
        expected_source_kinds=["stat"],
        reference="points gap + tactical needs; speculative-shaped but constructive",
    ),
    EvalQuery(
        id="amb-005",
        category="ambiguous",
        query="do you think Mainoo is overrated",
        expected_routes=["tactical_rag", "recent_rag"],
        expected_source_kinds=["chunk"],
        reference="opinion-shaped — should ground in what sources actually say about his output",
    ),

    # ----- out-of-scope (should refuse) -----
    EvalQuery(
        id="ofs-001",
        category="out_of_scope",
        query="who won the F1 last weekend",
        expected_routes=["refuse"],
        allow_refuse=True,
        reference="different sport, must refuse politely",
    ),
    EvalQuery(
        id="ofs-002",
        category="out_of_scope",
        query="what's Arsenal's pressing scheme",
        expected_routes=["refuse"],
        allow_refuse=True,
        reference="rival club without united context, must refuse",
    ),
    EvalQuery(
        id="ofs-003",
        category="out_of_scope",
        query="explain quantum entanglement",
        expected_routes=["refuse"],
        allow_refuse=True,
        reference="completely off-topic, must refuse",
    ),
    EvalQuery(
        id="ofs-004",
        category="out_of_scope",
        query="what's the weather like",
        expected_routes=["refuse"],
        allow_refuse=True,
        reference="off-topic, must refuse",
    ),
    EvalQuery(
        id="ofs-005",
        category="out_of_scope",
        query="who's the best in the NBA right now",
        expected_routes=["refuse"],
        allow_refuse=True,
        reference="different sport, refuse",
    ),

    # ----- adjacent-but-valid (should NOT refuse) -----
    EvalQuery(
        id="adj-001",
        category="ambiguous",
        query="how do we line up against Arsenal",
        expected_routes=["tactical_rag", "recent_rag"],
        expected_source_kinds=["chunk"],
        reference="united's setup VS arsenal — about us, not them, so valid",
    ),
    EvalQuery(
        id="adj-002",
        category="ambiguous",
        query="do you think we can beat Liverpool",
        expected_routes=["tactical_rag", "stats"],
        expected_source_kinds=["chunk", "stat"],
        reference="speculative but united-centric, ground in form + recent meetings",
    ),
]