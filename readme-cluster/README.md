# readme-cluster

Embed every dev project's README with OpenRouter, then cluster them, query them
under an ad-hoc lens, or ask a natural-language question. Each README is embedded
once per *scope* (an instruction lens), so the same projects rank and group
differently depending on which lens you look through.

## How it works

For each README and scope, the README is embedded with an instruction prepended
(Qwen3-Embedding's `Instruct: {task}\nQuery: {text}` format) against OpenRouter's
OpenAI-compatible `/embeddings` endpoint. Misses are embedded concurrently and
cached on disk. Clustering uses EVoC (Tutte Institute), which is built to cluster
embedding vectors directly and avoids the noise blow-up that density clustering
suffers in high-dimensional embedding space.

Scopes (default): `purpose`, `techniques`, `domain`. A scope instruction is free
text, so any lens works, including ones an LLM invents per question.

## Caching

Every embedding is cached in `cache/embeddings.json`, keyed by SHA-256 of
`(model, dimensions, exact input text)`. The scope instruction is part of the
input text, so changing the lens correctly produces new embeddings while an
unchanged README under a seen scope is never re-embedded. Each run prints
`cache: N hit / M miss`; a warm full run is ~1.7s vs ~32s cold.

## Subcommands

```sh
export OPENROUTER_API_KEY=...        # lives in ~/.localrc

# cluster (EVoC; clusters labeled by their medoid project)
./cluster.py cluster                                  # all scopes
./cluster.py cluster --scopes purpose --k 10          # finer, approx 10 clusters
./cluster.py cluster --scopes "ml=the machine learning method used"

# query: rank projects under one explicit lens
./cluster.py query "approximate nearest neighbor search" \
    --scope "the search/indexing technique this project implements" --top 8
./cluster.py query "tools that talk to an LLM" --json

# ask: a planner LLM derives the scope(s) + query from a question, then fuses
./cluster.py ask "which projects could help build code search" --top 6
./cluster.py ask "tools for ranking LLM outputs" --json
```

Shared flags (before the subcommand): `--model`, `--dimensions`, `--root`.

## Combining multiple scopes (for agent consumers)

`ask` lets the planner pick 1-3 complementary lenses. Cosine ranges differ per
lens, so raw scores are not comparable across scopes; fusion therefore defaults
to Reciprocal Rank Fusion (`--combine rrf`), which combines per-lens *ranks* and
is scale-free. `mean` and `max` are available. The JSON output always returns the
per-scope `rank` and `cosine` for each project, so a consuming agent can see
which lens drove a hit and re-weight if it wants:

```json
{"question": "...", "plan": {"scopes": ["..."], "query": "..."},
 "combine": "rrf",
 "results": [{"project": "vicinity", "score": 0.031,
              "scopes": [{"scope": "...", "rank": 0, "cosine": 0.74}]}]}
```

## Models (all on OpenRouter)

- Default embeddings: `qwen/qwen3-embedding-8b` (4096-dim, 32k context, ~$0.01/1M tokens).
- Code-aware embeddings: `mistralai/codestral-embed-2505`, `google/gemini-embedding-2`.
- Planner (`ask`): any chat model via `--planner` (default `openai/gpt-4o-mini`).

## Output

- `cluster`: clusters per scope (`~<medoid> (size)` then members) and
  `out/clusters.json` (per-project labels + groups with medoid).
- `query` / `ask`: ranked `score project` lines, or `--json` for agentic use.

Cost is a fraction of a cent per cold full run; warm runs are free.
