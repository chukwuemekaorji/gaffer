-- gaffer initial schema
-- run this once against a fresh supabase database. idempotent where it can be

-- pgvector for embeddings. supabase has this installed but the extension
-- still needs to be enabled in the database itself
create extension if not exists vector;


-- documents: top-level metadata about an ingested source
-- ============================================================
-- one row per article / tactical primer / match report.
-- the actual searchable content lives in chunks, not here.
create table if not exists documents (
    id              bigserial primary key,
    url             text unique,                -- null for tactical primers that aren't web sources
    title           text not null,
    source          text not null,              -- e.g. 'bbc_sport', 'the_athletic', 'curated_corpus'
    doc_type        text not null,              -- 'news', 'match_report', 'tactical_primer', 'player_profile', 'interview'
    published_at    timestamptz,
    ingested_at     timestamptz not null default now(),
    -- jsonb for anything source-specific we don't want to normalise:
    -- author, tags, raw rss entry, etc.
    extra           jsonb default '{}'::jsonb
);

create index if not exists documents_published_at_idx on documents (published_at desc);
create index if not exists documents_doc_type_idx on documents (doc_type);
create index if not exists documents_source_idx on documents (source);

-- ============================================================
-- chunks: the units of retrieval
-- ============================================================
-- each chunk carries its own metadata so we can filter before
-- semantic search rather than retrieving + filtering after.
create table if not exists chunks (
    id              bigserial primary key,
    document_id     bigint not null references documents(id) on delete cascade,
    chunk_index     int not null,                       -- order within the parent doc
    content         text not null,
    -- voyage-3-large outputs 1024-dim vectors. if we change embedding model
    -- we'll need a new column or a migration. living with that for now.
    embedding       vector(1024),
    -- filtering metadata. denormalised from documents on purpose so the planner
    -- can use these without a join during hot-path retrieval.
    era             text,                               -- 'ten_hag' | 'amorim' | 'carrick' | null for evergreen
    season          text,                               -- '2024-25', '2025-26'
    topic           text,                               -- 'pressing', 'transitions', 'set_pieces', etc
    players_mentioned text[] default '{}',              -- ['mainoo', 'bruno_fernandes']
    competition     text,                               -- 'premier_league', 'champions_league', 'fa_cup'
    match_id        bigint,                             -- nullable fk to matches, populated for match reports
    published_at    timestamptz,                        -- duplicated from documents for recency scoring
    token_count     int,                                -- useful for cost estimation later
    created_at      timestamptz not null default now()
);

-- the all-important vector index. ivfflat is the right call here:
-- - hnsw would be slightly faster at query time but slower to build and
--   takes more memory, both of which we feel on the free tier.
-- - ivfflat lists=100 is a fine starting point for ~10-50k chunks.
--   we'll retune once we have real data.
create index if not exists chunks_embedding_idx
    on chunks
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- btree indexes on the columns we'll filter by most.
create index if not exists chunks_era_idx          on chunks (era);
create index if not exists chunks_topic_idx        on chunks (topic);
create index if not exists chunks_published_at_idx on chunks (published_at desc);
create index if not exists chunks_match_id_idx     on chunks (match_id);
-- gin index for the players_mentioned array so 'where ? = any(players_mentioned)'
-- is fast. without this, player-filtered queries do a full table scan.
create index if not exists chunks_players_gin_idx  on chunks using gin (players_mentioned);

-- full-text index for bm25's keyword half. tsvector gives us postgres-native
-- text search; we'll generate the actual bm25 scores in python with rank-bm25
-- on the candidate set returned from this index, which keeps the implementation
-- simple and the retrieval explainable.
create index if not exists chunks_content_fts_idx
    on chunks
    using gin (to_tsvector('english', content));

-- ============================================================
-- fixtures: structured fixture / result data
-- ============================================================
-- one row per match united play. populated from football-data.org.
-- query patterns: "next fixture", "last result", "fixture by date".
create table if not exists fixtures (
    id              bigserial primary key,
    external_id     bigint unique,                  -- football-data.org match id, for upserts
    competition     text not null,                  -- 'premier_league', 'champions_league', etc
    season          text not null,
    matchday        int,
    kickoff_utc     timestamptz not null,
    home_team       text not null,
    away_team       text not null,
    home_score      int,                            -- null until match is finished
    away_score      int,
    status          text not null,                  -- 'scheduled', 'in_play', 'finished', 'postponed'
    venue           text,
    updated_at      timestamptz not null default now()
);

create index if not exists fixtures_kickoff_idx on fixtures (kickoff_utc);
create index if not exists fixtures_status_idx  on fixtures (status);

-- ============================================================
-- matches: ties fixtures to ingested reports
-- ============================================================
-- a fixture is the structured fact ("we played liverpool"); a match
-- is the narrative around it ("here's what people wrote about it").
-- separating these means the agent can answer factual questions from
-- fixtures even if no match report has been ingested yet.
create table if not exists matches (
    id              bigserial primary key,
    fixture_id      bigint not null references fixtures(id) on delete cascade,
    report_ingestion_status text not null default 'pending',  -- 'pending', 'in_progress', 'complete', 'failed'
    last_report_ingested_at timestamptz,
    notes           text
);

create index if not exists matches_fixture_id_idx on matches (fixture_id);

-- ============================================================
-- league_table: current standings, refreshed hourly
-- ============================================================
-- we only keep the current snapshot. historical positions can be
-- recomputed from match results if we ever need them.
create table if not exists league_table (
    id              bigserial primary key,
    competition     text not null,
    season          text not null,
    position        int not null,
    team            text not null,
    played          int not null,
    won             int not null,
    drawn           int not null,
    lost            int not null,
    goals_for       int not null,
    goals_against   int not null,
    goal_difference int not null,
    points          int not null,
    form            text,                           -- 'wwdlw' style string
    updated_at      timestamptz not null default now(),
    unique (competition, season, team)              -- upsert key
);

create index if not exists league_table_position_idx on league_table (competition, season, position);

-- ============================================================
-- player_season_stats: per-player aggregates for the current season
-- ============================================================
-- another snapshot table. answers questions like "how many goals does
-- bruno have this season". populated from soccerdata (fbref).
create table if not exists player_season_stats (
    id              bigserial primary key,
    season          text not null,
    competition     text not null,
    player_name     text not null,
    position        text,                           -- 'fw', 'mf', 'df', 'gk'
    appearances     int default 0,
    minutes         int default 0,
    goals           int default 0,
    assists         int default 0,
    yellow_cards    int default 0,
    red_cards       int default 0,
    expected_goals  numeric(5,2),
    expected_assists numeric(5,2),
    -- jsonb for advanced stats that vary by position
    -- (gks have saves; fwds have shots; etc). don't want a 50-column table.
    advanced        jsonb default '{}'::jsonb,
    updated_at      timestamptz not null default now(),
    unique (season, competition, player_name)
);

create index if not exists player_stats_player_idx on player_season_stats (player_name);

-- ============================================================
-- query_log: every query the agent answers, for evals + observability
-- ============================================================
-- langfuse will get the rich trace data. this is the local copy we own,
-- queryable with sql for ad-hoc analysis ("what % of queries hit the cache",
-- "what's the avg latency by route").
create table if not exists query_log (
    id              bigserial primary key,
    user_query      text not null,
    route           text[],                         -- ['stats', 'tactical_rag'] etc
    retrieved_chunk_ids bigint[],
    cache_hit       boolean default false,
    web_search_used boolean default false,
    answer          text,
    latency_ms      int,
    total_input_tokens  int,
    total_output_tokens int,
    estimated_cost_usd  numeric(8,5),
    created_at      timestamptz not null default now()
);

create index if not exists query_log_created_at_idx on query_log (created_at desc);