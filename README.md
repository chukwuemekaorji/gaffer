# Gaffer

a grounded ai tactical analyst for manchester united. ask it anything from
"how does carrick's setup differ from amorim's 3-4-3" to "how did mainoo play
yesterday" and it answers with citations, grounded in real data — never made up.

## why it exists

most rag chatbots i've seen hallucinate the moment you push them on specifics.
gaffer takes the opposite stance: every claim has to point back to a real
source — a stats api, a tactical document, or a match report — and the agent
refuses to answer when it can't ground itself.

the project also takes advantage of a uniquely interesting moment at united —
three managers in 18 months (ten hag → amorim → carrick) — so the comparative
axis across regimes is baked into the data model.

## what it does

- tactical analysis grounded in a curated knowledge base
- post-match conversation pulled from ingested match reports
- live league position, fixtures, results, and player stats via football-data.org
- transfer and news context from continuously-ingested rss feeds
- web search fallback for breaking news in the last ~24 hours

## stack

- **backend**: fastapi, python 3.12
- **frontend**: next.js 14 (app router), tailwind
- **llms**: claude sonnet 4.6 (generation), claude haiku 4.5 (routing, rewriting, judging)
- **embeddings**: voyage `voyage-3-large`
- **reranker**: cohere rerank 3
- **vector + relational db**: postgres + pgvector (supabase)
- **retrieval**: custom hybrid (pgvector + bm25 via rank-bm25), fused with rrf
- **ingestion**: prefect 2.x, feedparser, trafilatura
- **cache + rate limiting**: upstash redis
- **observability**: langfuse
- **evals**: custom harness + ragas

## status

work in progress. building this in sections — see the commit history for the
journey.

## evaluation

gaffer is evaluated against a stratified set of 40 queries across six categories: tactical, stats, recent events, comparisons, ambiguous routing, and out-of-scope refusals.

| config        | recall@5 | mrr   | route match | kind match | refusal | faithfulness | avg ms |
|---------------|---------:|------:|------------:|-----------:|--------:|-------------:|-------:|
| naive         | 0.45     | 0.22  | –           | –          | –       | –            | 314    |
| + hybrid      | 0.58     | 0.30  | –           | –          | –       | –            | 678    |
| + rerank      | 0.67     | 0.41  | –           | –          | –       | –            | 1240   |
| + rewriting   | 0.69     | 0.43  | –           | –          | –       | –            | 1854   |
| full system   | 0.70     | 0.44  | 0.83        | 0.79       | 0.91    | 0.87         | 4221   |

run yourself: `python -m scripts.run_evals` from `backend/`. dataset is in `app/evals/dataset.py`.

## running locally

prerequisites: python 3.11, node 20, a supabase project, and the api keys
listed in `.env.example`.

```powershell
# backend
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## license

MIT