# scry

Scry your project corpus. Embeds each project's README under one or more *scopes*
(instruction lenses) via OpenRouter, then clusters them, ranks them against a
query, or answers a natural-language question by letting a planner LLM choose the
lenses. Embeddings are cached on disk so unchanged inputs are never re-embedded.

The distinguishing idea is the scope: an instruction (purpose / techniques /
domain, or any free text) prepended to each document before embedding, so the
same corpus ranks and groups differently depending on the lens.

## Build

```sh
cargo build --release        # binary at target/release/scry
export OPENROUTER_API_KEY=... # lives in ~/.localrc
```

Clustering reuses the [`clump`](https://github.com/arclabs561/clump) crate (EVoC);
it is an unpublished sibling, so the dependency is a `path` and this crate is
local-only.

## Subcommands

```sh
# cluster (EVoC; clusters labeled by their medoid project)
scry cluster
scry cluster --scopes purpose --k 10
scry cluster --scopes "ml=the machine learning method used"

# query: rank projects under one explicit lens
scry query "approximate nearest neighbor search" \
    --scope "the search/indexing technique this project implements" --top 8
scry query "tools that talk to an LLM" --json

# ask: a planner LLM derives the scope(s) + query, then fuses (dual-LLM)
scry ask "which projects could help build code search" --top 6
scry ask "tools for ranking LLM outputs" --json
```

Shared flags (before the subcommand): `--root` (default `~/Documents/dev`),
`--model` (default `qwen/qwen3-embedding-8b`), `--dimensions` (Matryoshka
truncation).

## Combining multiple scopes

`ask` lets the planner pick 1-3 lenses. Cosine ranges differ per lens, so raw
scores are not comparable across scopes; fusion defaults to Reciprocal Rank
Fusion (`--combine rrf`), which combines per-lens *ranks* and is scale-free.
`mean` and `max` are available. The JSON output always returns each project's
per-scope `rank` and `cosine`, so a consuming agent sees which lens drove a hit:

```json
{"question":"...","plan":{"scopes":["..."],"query":"..."},"combine":"rrf",
 "results":[{"project":"rankit","score":0.0333,
             "scopes":[{"scope":"...","rank":0,"cosine":0.66}]}]}
```

## Models (all on OpenRouter)

- Default embeddings: `qwen/qwen3-embedding-8b` (4096-dim, 32k context).
- Code-aware embeddings: `mistralai/codestral-embed-2505`, `google/gemini-embedding-2`.
- Planner (`ask`): any chat model via `--planner` (default `openai/gpt-4o-mini`).

## Cache

`~/.cache/scry/embeddings.json`, keyed by SHA-256 of `(model, dimensions, exact
input text)`. The scope instruction is part of the input, so changing the lens
correctly produces new embeddings. Each run prints `cache: N hit / M miss`.
