#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "numpy>=1.26", "evoc>=0.3", "matplotlib"]
# ///
"""Scoped, instruction-conditioned embeddings of dev-project READMEs.

Each README is embedded once per *scope* (an instruction lens such as purpose /
techniques / domain). The same projects rank and group differently depending on
the lens you look through. Embeddings come from OpenRouter (OpenAI-compatible
/embeddings) and are cached on disk keyed by (model, dimensions, exact input
text), so unchanged READMEs are never re-embedded.

Two subcommands:

    cluster   embed all projects per scope and cluster them (EVoC)
    query     rank projects by relevance to an ad-hoc query under a scope lens

The scope instruction is free text, so an agent can pass any lens it wants:

    ./cluster.py query "approximate nearest neighbor search" \\
        --scope "the search/indexing technique this project implements"
    ./cluster.py query "tools that talk to an LLM" --json
    ./cluster.py cluster --scopes purpose,techniques,domain --k 10
    ./cluster.py cluster --scopes "ml=the machine learning method used"

Reads OPENROUTER_API_KEY from the environment (it lives in ~/.localrc).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_PLANNER = "openai/gpt-4o-mini"
TOOL_DIR = Path(__file__).resolve().parent
DEV_ROOT = TOOL_DIR.parent.parent  # toolbox/readme-cluster -> toolbox -> dev
CACHE_PATH = TOOL_DIR / "cache" / "embeddings.json"

# Named scope shorthands. A scope is "name -> instruction"; the instruction is
# prepended to text in Qwen3-Embedding's "Instruct: {task}\nQuery: {text}" form.
DEFAULT_SCOPES: dict[str, str] = {
    "purpose": "Represent this software project by its core purpose and the problem it solves.",
    "techniques": "Represent this software project by the algorithms, methods, and technical techniques it uses.",
    "domain": "Represent this software project by its subject domain and the field it belongs to.",
}

SKIP_PREFIXES = ("_", ".")
SKIP_NAMES = {"target", "node_modules", "readme-cluster"}

CHAR_BUDGET = 24_000
BATCH_SIZE = 32
CONCURRENCY = 6
RRF_K = 60  # reciprocal-rank-fusion constant; standard default


# --------------------------------------------------------------------------- #
# project discovery
# --------------------------------------------------------------------------- #
@dataclass
class Project:
    name: str
    readme: str


def discover_projects(root: Path) -> list[Project]:
    projects: list[Project] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name in SKIP_NAMES or d.name.startswith(SKIP_PREFIXES):
            continue
        readme = next((f for f in sorted(d.glob("README*")) if f.is_file()), None)
        if readme is None:
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            projects.append(Project(name=d.name, readme=text[:CHAR_BUDGET]))
    return projects


def parse_scopes(spec: str) -> dict[str, str]:
    """Each comma item is either a named default or 'name=free instruction'."""
    scopes: dict[str, str] = {}
    for item in (s.strip() for s in spec.split(",") if s.strip()):
        if "=" in item:
            name, instr = item.split("=", 1)
            scopes[name.strip()] = instr.strip()
        elif item in DEFAULT_SCOPES:
            scopes[item] = DEFAULT_SCOPES[item]
        else:
            sys.exit(
                f"unknown scope {item!r}; use a default {list(DEFAULT_SCOPES)} "
                f"or 'name=instruction'"
            )
    return scopes


def format_input(instruction: str, text: str) -> str:
    return f"Instruct: {instruction}\nQuery: {text}"


# --------------------------------------------------------------------------- #
# cache + embedding
# --------------------------------------------------------------------------- #
class Cache:
    """Disk-backed map of input-hash -> embedding vector."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, list[float]] = {}
        self.hits = 0
        self.misses = 0
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                self.data = {}

    @staticmethod
    def key(model: str, dimensions: int | None, text: str) -> str:
        h = hashlib.sha256()
        h.update(f"{model}\x00{dimensions}\x00".encode())
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data))
        tmp.replace(self.path)


async def _embed_batch(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    model: str,
    dimensions: int | None,
    inputs: list[str],
) -> list[list[float]]:
    body: dict = {"model": model, "input": inputs}
    if dimensions:
        body["dimensions"] = dimensions
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.post(OPENROUTER_URL, json=body)
                resp.raise_for_status()
                data = resp.json()["data"]
                data.sort(key=lambda r: r["index"])
                return [r["embedding"] for r in data]
            except (httpx.HTTPError, KeyError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt)
    raise RuntimeError("unreachable")


async def embed_texts(
    texts: list[str], model: str, dimensions: int | None, cache: Cache
) -> np.ndarray:
    """Return a matrix of embeddings for `texts`, embedding only cache misses.

    All miss-batches run concurrently. The cache is consulted per unique text,
    so repeated inputs cost nothing.
    """
    keys = [Cache.key(model, dimensions, t) for t in texts]
    present = sum(1 for k in keys if k in cache.data)
    cache.hits += present
    cache.misses += len(keys) - present

    miss_order: list[str] = []  # unique missing texts, stable order
    miss_seen: set[str] = set()
    for t, k in zip(texts, keys, strict=False):
        if k not in cache.data and k not in miss_seen:
            miss_seen.add(k)
            miss_order.append(t)

    if miss_order:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            sys.exit("OPENROUTER_API_KEY not set (it lives in ~/.localrc).")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "readme-cluster",
        }
        sem = asyncio.Semaphore(CONCURRENCY)
        batches = [miss_order[i : i + BATCH_SIZE] for i in range(0, len(miss_order), BATCH_SIZE)]
        async with httpx.AsyncClient(headers=headers, timeout=120) as client:
            results = await asyncio.gather(
                *(_embed_batch(client, sem, model, dimensions, b) for b in batches)
            )
        for batch, vecs in zip(batches, results, strict=False):
            for t, v in zip(batch, vecs, strict=False):
                cache.data[Cache.key(model, dimensions, t)] = v
        cache.save()

    return np.array([cache.data[k] for k in keys], dtype=np.float32)


# --------------------------------------------------------------------------- #
# clustering
# --------------------------------------------------------------------------- #
def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def cluster_vectors(vecs: np.ndarray, k: int | None) -> np.ndarray:
    """Cluster embedding vectors with EVoC; -1 is noise.

    EVoC (Tutte Institute) is built to cluster embedding vectors directly via an
    ensemble of kNN graphs, so it needs no PCA crutch and avoids the noise
    blow-up HDBSCAN suffers on high-dimensional anisotropic embeddings.
    """
    from evoc import EVoC  # lazy: pulls numba

    return EVoC(approx_n_clusters=k).fit_predict(l2_normalize(vecs))


def medoid_labels(vecs: np.ndarray, labels: np.ndarray, names: list[str]) -> dict[int, str]:
    """Label each cluster by its medoid: the project nearest the centroid."""
    x = l2_normalize(vecs)
    out: dict[int, str] = {}
    for lab in sorted({int(v) for v in labels}):
        rows = np.where(labels == lab)[0]
        centroid = x[rows].mean(0)
        out[lab] = names[rows[int(np.argmax(x[rows] @ centroid))]]
    return out


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_cluster(args: argparse.Namespace) -> None:
    scopes = parse_scopes(args.scopes)
    projects = discover_projects(args.root)
    if not projects:
        sys.exit(f"no projects with READMEs under {args.root}")
    names = [p.name for p in projects]
    cache = Cache(CACHE_PATH)
    print(
        f"{len(projects)} projects · scopes={list(scopes)} · model={args.model}",
        file=sys.stderr,
    )

    clusters_json: dict[str, dict] = {}
    for scope, instr in scopes.items():
        inputs = [format_input(instr, p.readme) for p in projects]
        mat = asyncio.run(embed_texts(inputs, args.model, args.dimensions, cache))
        labels = cluster_vectors(mat, args.k)
        medoid = medoid_labels(mat, labels, names)

        groups: dict[int, list[str]] = {}
        for name, lab in zip(names, labels, strict=False):
            groups.setdefault(int(lab), []).append(name)
        clusters_json[scope] = {
            "labels": {name: int(lab) for name, lab in zip(names, labels, strict=False)},
            "groups": {
                str(lab): {"medoid": medoid[lab], "projects": members}
                for lab, members in sorted(groups.items())
            },
        }

        print(f"\n=== scope: {scope} ===")
        for lab in sorted(groups):
            tag = "noise" if lab == -1 else f"~{medoid[lab]}"
            print(f"  {tag} ({len(groups[lab])})")
            print(f"    {', '.join(sorted(groups[lab]))}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "clusters.json").write_text(json.dumps(clusters_json, indent=2))
    print(
        f"\ncache: {cache.hits} hit / {cache.misses} miss · wrote {args.out}/clusters.json",
        file=sys.stderr,
    )


def cmd_query(args: argparse.Namespace) -> None:
    instr = DEFAULT_SCOPES.get(args.scope, args.scope)
    projects = discover_projects(args.root)
    if not projects:
        sys.exit(f"no projects with READMEs under {args.root}")
    names = [p.name for p in projects]
    cache = Cache(CACHE_PATH)

    doc_inputs = [format_input(instr, p.readme) for p in projects]
    q_input = format_input(instr, args.text)
    docs = asyncio.run(embed_texts(doc_inputs, args.model, args.dimensions, cache))
    q = asyncio.run(embed_texts([q_input], args.model, args.dimensions, cache))[0]

    sims = l2_normalize(docs) @ (q / (np.linalg.norm(q) or 1.0))
    order = np.argsort(sims)[::-1][: args.top]
    results = [{"project": names[i], "score": round(float(sims[i]), 4)} for i in order]

    if args.json:
        print(json.dumps({"query": args.text, "scope": instr, "results": results}))
    else:
        print(f"query: {args.text!r}", file=sys.stderr)
        print(f"scope: {instr!r}", file=sys.stderr)
        for r in results:
            print(f"  {r['score']:.4f}  {r['project']}")
    print(f"cache: {cache.hits} hit / {cache.misses} miss", file=sys.stderr)


def plan_scopes(question: str, planner: str) -> dict:
    """Dual-LLM step: a planner model turns a natural-language question into 1-3
    scope lenses plus a query string. The model emits structured intent only;
    this tool executes the (read-only) retrieval. Returns {scopes, query}.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY not set (it lives in ~/.localrc).")
    sys_prompt = (
        "You turn a question about a collection of software projects into a "
        'retrieval plan. Output ONLY JSON: {"scopes": ["<lens instruction>", ...], '
        '"query": "<search text>"}. Each scope is a short instruction naming the '
        "ASPECT to match on (its purpose, the technique it uses, its domain, the "
        "data structure, etc.) phrased like 'Represent this project by ...'. Use "
        "1-3 complementary scopes when the question spans aspects, else 1. The "
        "query is the thing to look for under those lenses."
    )
    body = {
        "model": planner,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    with httpx.Client(timeout=60) as client:
        r = client.post(
            OPENROUTER_CHAT_URL,
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "readme-cluster"},
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    plan = json.loads(content)
    scopes = [s for s in plan.get("scopes", []) if isinstance(s, str) and s.strip()]
    return {
        "scopes": scopes or ["Represent this project by its core purpose."],
        "query": plan.get("query") or question,
    }


def cmd_ask(args: argparse.Namespace) -> None:
    plan = plan_scopes(args.text, args.planner)
    scopes, query = plan["scopes"], plan["query"]
    projects = discover_projects(args.root)
    if not projects:
        sys.exit(f"no projects with READMEs under {args.root}")
    names = [p.name for p in projects]
    cache = Cache(CACHE_PATH)
    print(
        f"planner={args.planner} · {len(scopes)} scope(s) · combine={args.combine} "
        f"· query={query!r}",
        file=sys.stderr,
    )

    # Per scope: cosine to the query and the project's rank under that lens.
    # Scores are NOT comparable across scopes (different cosine ranges), so the
    # default fusion is RRF over ranks, which is scale-free. Per-scope detail is
    # returned so the consuming agent sees which lens drove each hit.
    fused = {n: 0.0 for n in names}
    per_scope: dict[str, list[dict]] = {n: [] for n in names}
    for instr in scopes:
        docs = asyncio.run(
            embed_texts(
                [format_input(instr, p.readme) for p in projects],
                args.model,
                args.dimensions,
                cache,
            )
        )
        qv = asyncio.run(
            embed_texts([format_input(instr, query)], args.model, args.dimensions, cache)
        )[0]
        sims = l2_normalize(docs) @ (qv / (np.linalg.norm(qv) or 1.0))
        ranks = {int(idx): r for r, idx in enumerate(np.argsort(sims)[::-1])}
        for i, n in enumerate(names):
            cos, rank = float(sims[i]), ranks[i]
            per_scope[n].append({"scope": instr, "rank": rank, "cosine": round(cos, 4)})
            if args.combine == "rrf":
                fused[n] += 1.0 / (RRF_K + rank)
            elif args.combine == "max":
                fused[n] = max(fused[n], cos)
            else:  # mean
                fused[n] += cos / len(scopes)

    ranked = sorted(names, key=lambda n: fused[n], reverse=True)[: args.top]
    results = [
        {
            "project": n,
            "score": round(fused[n], 5),
            "scopes": sorted(per_scope[n], key=lambda d: d["rank"]),
        }
        for n in ranked
    ]
    if args.json:
        print(
            json.dumps(
                {"question": args.text, "plan": plan, "combine": args.combine, "results": results}
            )
        )
    else:
        print(f"Q: {args.text}", file=sys.stderr)
        for s in scopes:
            print(f"  lens: {s}", file=sys.stderr)
        for n in ranked:
            top = min(per_scope[n], key=lambda d: d["rank"])
            print(f"  {fused[n]:.4f}  {n:16s} (via '{top['scope'][:38]}…' #{top['rank']})")
    print(f"cache: {cache.hits} hit / {cache.misses} miss", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", type=Path, default=DEV_ROOT, help="dir of project subdirs")
    ap.add_argument("--model", default="qwen/qwen3-embedding-8b")
    ap.add_argument("--dimensions", type=int, default=None, help="truncate embedding dim")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cluster", help="embed all projects per scope and cluster (EVoC)")
    c.add_argument(
        "--scopes",
        default=",".join(DEFAULT_SCOPES),
        help="comma list of named scopes or name=instruction pairs",
    )
    c.add_argument("--k", type=int, default=None, help="approximate cluster-count hint")
    c.add_argument("--out", type=Path, default=TOOL_DIR / "out")
    c.set_defaults(func=cmd_cluster)

    q = sub.add_parser("query", help="rank projects by relevance under a scope lens")
    q.add_argument("text", help="the query text")
    q.add_argument("--scope", default="purpose", help="named scope or free-text instruction lens")
    q.add_argument("--top", type=int, default=10)
    q.add_argument("--json", action="store_true", help="emit JSON for agentic use")
    q.set_defaults(func=cmd_query)

    a = sub.add_parser(
        "ask", help="dual-LLM: a planner derives scope(s)+query from a question, then fuses"
    )
    a.add_argument("text", help="natural-language question")
    a.add_argument("--planner", default=DEFAULT_PLANNER, help="OpenRouter chat model")
    a.add_argument(
        "--combine",
        choices=["rrf", "mean", "max"],
        default="rrf",
        help="how to fuse multiple scopes (rrf = rank fusion, scale-free)",
    )
    a.add_argument("--top", type=int, default=10)
    a.add_argument("--json", action="store_true", help="emit JSON for agentic use")
    a.set_defaults(func=cmd_ask)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
