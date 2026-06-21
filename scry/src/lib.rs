//! # scry
//!
//! Scry your project corpus: scoped, instruction-conditioned embeddings of
//! dev-project docs, with EVoC clustering and a dual-LLM "ask" front-end, all
//! over OpenRouter. Reuses [`clump`] for clustering and talks to OpenRouter
//! directly via [`openrouter`].
//!
//! The central idea is the *scope*: an instruction lens (purpose / techniques /
//! domain, or any free-text instruction) prepended to each README before
//! embedding, so the same corpus ranks and groups differently per lens.
//!
//! Pipeline:
//! 1. [`corpus::discover`] finds projects with READMEs.
//! 2. [`embed_texts`] embeds them per scope, concurrently, through a disk
//!    [`cache::Cache`] so unchanged inputs are never re-embedded.
//! 3. [`cluster_labels`] groups one scope's vectors with EVoC; [`medoid_labels`]
//!    names each cluster by its most central project.
//! 4. [`rank`] scores projects against a query under one lens; [`rrf_fuse`]
//!    combines several lenses by Reciprocal Rank Fusion (scale-free, the right
//!    way to merge rankings whose score ranges differ per lens).

pub mod cache;
pub mod code;
pub mod corpus;
pub mod openrouter;

use anyhow::{Context, Result};
use cache::Cache;
use clump::{EVoC, EVoCParams};
use corpus::Project;
use futures::stream::{self, StreamExt};
use openrouter::Client;

const BATCH_SIZE: usize = 32;
const CONCURRENCY: usize = 6;
/// Reciprocal-rank-fusion constant; the standard default.
pub const RRF_K: f32 = 60.0;

/// Embed `texts`, returning one vector per input, embedding only cache misses.
///
/// Misses are batched and the batches run concurrently (bounded by
/// [`CONCURRENCY`]). The cache is consulted per unique text, so repeated inputs
/// cost nothing, and it is saved once after the misses resolve.
pub async fn embed_texts(
    client: &Client,
    cache: &mut Cache,
    model: &str,
    dimensions: Option<u32>,
    texts: &[String],
) -> Result<Vec<Vec<f32>>> {
    let keys: Vec<String> = texts
        .iter()
        .map(|t| Cache::key(model, dimensions, t))
        .collect();
    let present = keys.iter().filter(|k| cache.map.contains_key(*k)).count();
    cache.hits += present;
    cache.misses += keys.len() - present;

    let mut miss_texts: Vec<String> = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for (t, k) in texts.iter().zip(&keys) {
        if !cache.map.contains_key(k) && seen.insert(k.clone()) {
            miss_texts.push(t.clone());
        }
    }

    if !miss_texts.is_empty() {
        let batches: Vec<Vec<String>> = miss_texts.chunks(BATCH_SIZE).map(|c| c.to_vec()).collect();
        let results: Vec<Vec<Vec<f32>>> = stream::iter(batches.iter())
            .map(|b| async move { client.embed(model, dimensions, b).await })
            .buffered(CONCURRENCY)
            .collect::<Vec<_>>()
            .await
            .into_iter()
            .collect::<Result<Vec<_>>>()?;
        for (batch, vecs) in batches.iter().zip(results) {
            for (t, v) in batch.iter().zip(vecs) {
                cache.map.insert(Cache::key(model, dimensions, t), v);
            }
        }
        cache.save().context("save cache")?;
    }

    Ok(keys.iter().map(|k| cache.map[k].clone()).collect())
}

/// Embed the `code` surface: one mean-pooled vector per project, built from its
/// source-file chunks (embedded with `model`, typically a code model). Chunks
/// are embedded through the same cache. Returns `(vectors, capped, codeless)`:
/// how many projects hit the per-project chunk cap, and how many had no source
/// at all (those get a zero vector and sort last / cluster as noise).
pub async fn embed_code(
    client: &Client,
    cache: &mut Cache,
    model: &str,
    dimensions: Option<u32>,
    projects: &[Project],
) -> Result<(Vec<Vec<f32>>, usize, usize)> {
    let mut all_chunks: Vec<String> = Vec::new();
    let mut counts: Vec<usize> = Vec::with_capacity(projects.len());
    let mut capped = 0usize;
    for p in projects {
        let (chunks, was_capped) = code::gather_chunks(&p.dir);
        if was_capped {
            capped += 1;
        }
        counts.push(chunks.len());
        all_chunks.extend(chunks);
    }
    if all_chunks.is_empty() {
        anyhow::bail!("no source files found under any project");
    }
    let chunk_vecs = embed_texts(client, cache, model, dimensions, &all_chunks).await?;
    let dim = chunk_vecs[0].len();

    let mut vectors = Vec::with_capacity(projects.len());
    let mut codeless = 0usize;
    let mut offset = 0usize;
    for &count in &counts {
        if count == 0 {
            codeless += 1;
            vectors.push(vec![0.0f32; dim]);
            continue;
        }
        let mut pooled = vec![0.0f32; dim];
        for v in &chunk_vecs[offset..offset + count] {
            for (acc, x) in pooled.iter_mut().zip(v) {
                *acc += x;
            }
        }
        for acc in &mut pooled {
            *acc /= count as f32;
        }
        vectors.push(pooled);
        offset += count;
    }
    Ok((vectors, capped, codeless))
}

/// L2-normalize a vector (zero vectors are left unchanged).
pub fn l2_normalize(v: &[f32]) -> Vec<f32> {
    let norm = v.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm == 0.0 {
        v.to_vec()
    } else {
        v.iter().map(|x| x / norm).collect()
    }
}

/// Cosine similarity of every document against the query (all are normalized
/// internally). Returns one score per document, in document order.
pub fn cosine_scores(docs: &[Vec<f32>], query: &[f32]) -> Vec<f32> {
    let q = l2_normalize(query);
    docs.iter()
        .map(|d| {
            let dn = l2_normalize(d);
            dn.iter().zip(&q).map(|(a, b)| a * b).sum()
        })
        .collect()
}

/// Cluster one scope's embedding vectors with EVoC. Returns a label per vector;
/// `None` is noise. When `k` is given, the hierarchy is cut to approximately
/// that many clusters.
pub fn cluster_labels(vecs: &[Vec<f32>], k: Option<usize>) -> Result<Vec<Option<usize>>> {
    let normalized: Vec<Vec<f32>> = vecs.iter().map(|v| l2_normalize(v)).collect();
    let params = EVoCParams {
        min_cluster_size: 3,
        ..Default::default()
    };
    let mut model = EVoC::new(params);
    match k {
        Some(k) => {
            model.fit_predict(&normalized).context("evoc fit")?;
            Ok(model
                .layer_for_n_clusters(k)
                .context("evoc layer for k")?
                .assignments)
        }
        None => model.fit_predict(&normalized).context("evoc fit_predict"),
    }
}

/// Label each cluster by its medoid: the project nearest the cluster centroid.
/// `labels` aligns with `names`; `None` labels (noise) map to `usize::MAX`.
pub fn medoid_labels(
    vecs: &[Vec<f32>],
    labels: &[Option<usize>],
    names: &[String],
) -> std::collections::BTreeMap<i64, String> {
    use std::collections::BTreeMap;
    let normalized: Vec<Vec<f32>> = vecs.iter().map(|v| l2_normalize(v)).collect();
    let mut groups: BTreeMap<i64, Vec<usize>> = BTreeMap::new();
    for (i, lab) in labels.iter().enumerate() {
        let key = lab.map(|l| l as i64).unwrap_or(-1);
        groups.entry(key).or_default().push(i);
    }
    let mut out = BTreeMap::new();
    for (key, rows) in groups {
        let dim = normalized[rows[0]].len();
        let mut centroid = vec![0.0f32; dim];
        for &i in &rows {
            for (c, x) in centroid.iter_mut().zip(&normalized[i]) {
                *c += x;
            }
        }
        for c in &mut centroid {
            *c /= rows.len() as f32;
        }
        let best = rows
            .iter()
            .max_by(|&&a, &&b| {
                let sa: f32 = normalized[a]
                    .iter()
                    .zip(&centroid)
                    .map(|(x, y)| x * y)
                    .sum();
                let sb: f32 = normalized[b]
                    .iter()
                    .zip(&centroid)
                    .map(|(x, y)| x * y)
                    .sum();
                sa.total_cmp(&sb)
            })
            .copied()
            .unwrap_or(rows[0]);
        out.insert(key, names[best].clone());
    }
    out
}

/// Fuse per-scope rankings by Reciprocal Rank Fusion. `per_scope_ranks[s][i]` is
/// project `i`'s 0-based rank under scope `s`. Returns a fused score per project.
pub fn rrf_fuse(per_scope_ranks: &[Vec<usize>], n: usize) -> Vec<f32> {
    let mut fused = vec![0.0f32; n];
    for ranks in per_scope_ranks {
        for (i, &r) in ranks.iter().enumerate() {
            fused[i] += 1.0 / (RRF_K + r as f32);
        }
    }
    fused
}

/// Rank indices by descending score.
pub fn argsort_desc(scores: &[f32]) -> Vec<usize> {
    let mut idx: Vec<usize> = (0..scores.len()).collect();
    idx.sort_by(|&a, &b| scores[b].total_cmp(&scores[a]));
    idx
}

/// Dual-LLM planner: turn a natural-language question into 1-3 scope lenses plus
/// a query string. The model emits structured intent only; the caller executes
/// the read-only retrieval. Returns `(scopes, query)`.
pub async fn plan_scopes(
    client: &Client,
    planner: &str,
    question: &str,
) -> Result<(Vec<String>, String)> {
    let system = "You turn a question about a collection of software projects into a \
        retrieval plan. Output ONLY JSON: {\"scopes\": [\"<lens instruction>\", ...], \
        \"query\": \"<search text>\"}. Each scope is a short instruction naming the \
        ASPECT to match on (its purpose, the technique it uses, its domain, the data \
        structure, etc.) phrased like 'Represent this project by ...'. Use 1-3 \
        complementary scopes when the question spans aspects, else 1. The query is the \
        thing to look for under those lenses.";
    let content = client.chat_json(planner, system, question).await?;
    let parsed: serde_json::Value = serde_json::from_str(&content).context("parse plan JSON")?;
    let scopes: Vec<String> = parsed["scopes"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|s| s.as_str())
                .filter(|s| !s.trim().is_empty())
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default();
    let scopes = if scopes.is_empty() {
        vec!["Represent this project by its core purpose.".to_string()]
    } else {
        scopes
    };
    let query = parsed["query"]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .unwrap_or(question)
        .to_string();
    Ok((scopes, query))
}
