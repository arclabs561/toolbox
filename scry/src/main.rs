//! Command-line entry point: `cluster`, `query`, and `ask` subcommands.

use anyhow::{bail, Result};
use clap::{Parser, Subcommand};
use scry::{
    argsort_desc, cache::Cache, cluster_labels, corpus, cosine_scores, embed_code, embed_texts,
    medoid_labels, openrouter::Client, plan_scopes, rrf_fuse,
};
use std::collections::BTreeMap;
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    about = "Scoped README embeddings + EVoC clustering + dual-LLM ask, over OpenRouter",
    long_about = None
)]
struct Cli {
    /// Directory whose immediate subdirectories are projects (default: ~/Documents/dev).
    #[arg(long, global = true)]
    root: Option<PathBuf>,
    /// OpenRouter embedding model.
    #[arg(long, global = true, default_value = "qwen/qwen3-embedding-8b")]
    model: String,
    /// Optionally truncate the embedding dimension (Matryoshka).
    #[arg(long, global = true)]
    dimensions: Option<u32>,
    /// Embedding surface: `readme` (instruction-scoped) or `code` (source files).
    #[arg(long, global = true, default_value = "readme")]
    surface: String,
    /// Model for the `code` surface.
    #[arg(long, global = true, default_value = "mistralai/codestral-embed-2505")]
    code_model: String,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Embed all projects per scope and cluster them (EVoC).
    Cluster {
        /// Comma list of named scopes or `name=instruction` pairs.
        #[arg(long, default_value = "purpose,techniques,domain")]
        scopes: String,
        /// Approximate cluster-count hint.
        #[arg(long)]
        k: Option<usize>,
        /// Output directory for clusters.json.
        #[arg(long, default_value = "out")]
        out: PathBuf,
    },
    /// Rank projects by relevance to a query under one scope lens.
    Query {
        /// The query text.
        text: String,
        /// Named scope or free-text instruction lens.
        #[arg(long, default_value = "purpose")]
        scope: String,
        #[arg(long, default_value_t = 10)]
        top: usize,
        /// Emit JSON for agentic use.
        #[arg(long)]
        json: bool,
    },
    /// Dual-LLM: a planner derives scope(s)+query from a question, then fuses.
    Ask {
        /// Natural-language question.
        text: String,
        /// OpenRouter chat model used for planning.
        #[arg(long, default_value = "openai/gpt-4o-mini")]
        planner: String,
        /// How to fuse multiple scopes: rrf (rank fusion, scale-free), mean, or max.
        #[arg(long, default_value = "rrf")]
        combine: String,
        #[arg(long, default_value_t = 10)]
        top: usize,
        /// Emit JSON for agentic use.
        #[arg(long)]
        json: bool,
    },
}

/// Parse the cluster `--scopes` spec into `(name, instruction)` pairs.
fn parse_scopes(spec: &str) -> Result<Vec<(String, String)>> {
    let mut out = Vec::new();
    for item in spec.split(',').map(str::trim).filter(|s| !s.is_empty()) {
        if let Some((name, instr)) = item.split_once('=') {
            out.push((name.trim().to_string(), instr.trim().to_string()));
        } else if let Some((n, instr)) = corpus::DEFAULT_SCOPES.iter().find(|(n, _)| *n == item) {
            out.push((n.to_string(), instr.to_string()));
        } else {
            bail!("unknown scope {item:?}; use a default or 'name=instruction'");
        }
    }
    Ok(out)
}

/// Cluster one matrix, print the groups under `title`, and return the JSON.
fn cluster_and_emit(
    title: &str,
    mat: &[Vec<f32>],
    k: Option<usize>,
    names: &[String],
) -> Result<serde_json::Value> {
    let labels = cluster_labels(mat, k)?;
    let medoid = medoid_labels(mat, &labels, names);
    let mut groups: BTreeMap<i64, Vec<String>> = BTreeMap::new();
    for (n, lab) in names.iter().zip(&labels) {
        groups
            .entry(lab.map(|l| l as i64).unwrap_or(-1))
            .or_default()
            .push(n.clone());
    }
    println!("\n=== {title} ===");
    let mut group_json = serde_json::Map::new();
    for (key, members) in &groups {
        let mut sorted = members.clone();
        sorted.sort();
        let tag = if *key == -1 {
            "noise".to_string()
        } else {
            format!("~{}", medoid[key])
        };
        println!("  {} ({})", tag, members.len());
        println!("    {}", sorted.join(", "));
        group_json.insert(
            key.to_string(),
            serde_json::json!({ "medoid": medoid.get(key), "projects": sorted }),
        );
    }
    let label_map: serde_json::Map<String, serde_json::Value> = names
        .iter()
        .zip(&labels)
        .map(|(n, l)| {
            (
                n.clone(),
                serde_json::json!(l.map(|x| x as i64).unwrap_or(-1)),
            )
        })
        .collect();
    Ok(serde_json::json!({ "labels": label_map, "groups": group_json }))
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let root = cli.root.clone().unwrap_or_else(corpus::default_root);
    let client = Client::from_env()?;
    let mut cache = Cache::load(Cache::default_path());

    match &cli.cmd {
        Cmd::Cluster { scopes, k, out } => {
            let projects = corpus::discover(&root)?;
            if projects.is_empty() {
                bail!("no projects with READMEs under {}", root.display());
            }
            let names: Vec<String> = projects.iter().map(|p| p.name.clone()).collect();
            let mut clusters_json = serde_json::Map::new();

            if cli.surface == "code" {
                let (mat, capped, codeless) = embed_code(
                    &client,
                    &mut cache,
                    &cli.code_model,
                    cli.dimensions,
                    &projects,
                )
                .await?;
                eprintln!(
                    "{} projects · surface=code · model={} · {capped} capped / {codeless} codeless",
                    projects.len(),
                    cli.code_model
                );
                clusters_json.insert(
                    "code".into(),
                    cluster_and_emit("surface: code", &mat, *k, &names)?,
                );
            } else {
                let scopes = parse_scopes(scopes)?;
                eprintln!(
                    "{} projects · scopes={:?} · model={}",
                    projects.len(),
                    scopes.iter().map(|(n, _)| n).collect::<Vec<_>>(),
                    cli.model
                );
                for (name, instr) in &scopes {
                    let inputs: Vec<String> = projects
                        .iter()
                        .map(|p| corpus::format_input(instr, &p.readme))
                        .collect();
                    let mat = embed_texts(&client, &mut cache, &cli.model, cli.dimensions, &inputs)
                        .await?;
                    clusters_json.insert(
                        name.clone(),
                        cluster_and_emit(&format!("scope: {name}"), &mat, *k, &names)?,
                    );
                }
            }
            std::fs::create_dir_all(out)?;
            std::fs::write(
                out.join("clusters.json"),
                serde_json::to_vec_pretty(&clusters_json)?,
            )?;
            eprintln!(
                "\ncache: {} hit / {} miss · wrote {}/clusters.json",
                cache.hits,
                cache.misses,
                out.display()
            );
        }

        Cmd::Query {
            text,
            scope,
            top,
            json,
        } => {
            let projects = corpus::discover(&root)?;
            if projects.is_empty() {
                bail!("no projects with READMEs under {}", root.display());
            }
            let names: Vec<String> = projects.iter().map(|p| p.name.clone()).collect();
            let (docs, qv, scope_label) = if cli.surface == "code" {
                let (docs, capped, codeless) = embed_code(
                    &client,
                    &mut cache,
                    &cli.code_model,
                    cli.dimensions,
                    &projects,
                )
                .await?;
                eprintln!(
                    "surface=code · model={} · {capped} capped / {codeless} codeless",
                    cli.code_model
                );
                let qv = embed_texts(
                    &client,
                    &mut cache,
                    &cli.code_model,
                    cli.dimensions,
                    std::slice::from_ref(text),
                )
                .await?;
                (docs, qv, "code".to_string())
            } else {
                let instr = corpus::resolve_scope(scope);
                let doc_inputs: Vec<String> = projects
                    .iter()
                    .map(|p| corpus::format_input(&instr, &p.readme))
                    .collect();
                let docs =
                    embed_texts(&client, &mut cache, &cli.model, cli.dimensions, &doc_inputs)
                        .await?;
                let qv = embed_texts(
                    &client,
                    &mut cache,
                    &cli.model,
                    cli.dimensions,
                    &[corpus::format_input(&instr, text)],
                )
                .await?;
                (docs, qv, instr)
            };
            let scores = cosine_scores(&docs, &qv[0]);
            let order = argsort_desc(&scores);

            let results: Vec<_> = order
                .iter()
                .take(*top)
                .map(|&i| serde_json::json!({ "project": names[i], "score": (scores[i] * 1e4).round() / 1e4 }))
                .collect();
            if *json {
                println!(
                    "{}",
                    serde_json::json!({ "query": text, "scope": scope_label, "results": results })
                );
            } else {
                eprintln!("query: {text:?}\nscope: {scope_label:?}");
                for &i in order.iter().take(*top) {
                    println!("  {:.4}  {}", scores[i], names[i]);
                }
            }
            eprintln!("cache: {} hit / {} miss", cache.hits, cache.misses);
        }

        Cmd::Ask {
            text,
            planner,
            combine,
            top,
            json,
        } => {
            if cli.surface == "code" {
                eprintln!("note: ask uses the readme surface (code not supported for ask yet)");
            }
            let (scopes, query) = plan_scopes(&client, planner, text).await?;
            let projects = corpus::discover(&root)?;
            if projects.is_empty() {
                bail!("no projects with READMEs under {}", root.display());
            }
            let names: Vec<String> = projects.iter().map(|p| p.name.clone()).collect();
            let n = names.len();
            eprintln!(
                "planner={planner} · {} scope(s) · combine={combine} · query={query:?}",
                scopes.len()
            );

            let mut fused = vec![0.0f32; n];
            let mut per_scope_detail: Vec<Vec<serde_json::Value>> = vec![Vec::new(); n];
            let mut rank_lists: Vec<Vec<usize>> = Vec::new();
            for instr in &scopes {
                let doc_inputs: Vec<String> = projects
                    .iter()
                    .map(|p| corpus::format_input(instr, &p.readme))
                    .collect();
                let docs =
                    embed_texts(&client, &mut cache, &cli.model, cli.dimensions, &doc_inputs)
                        .await?;
                let qv = embed_texts(
                    &client,
                    &mut cache,
                    &cli.model,
                    cli.dimensions,
                    &[corpus::format_input(instr, &query)],
                )
                .await?;
                let scores = cosine_scores(&docs, &qv[0]);
                let order = argsort_desc(&scores);
                let mut rank_of = vec![0usize; n];
                for (r, &i) in order.iter().enumerate() {
                    rank_of[i] = r;
                }
                for i in 0..n {
                    per_scope_detail[i].push(serde_json::json!({
                        "scope": instr,
                        "rank": rank_of[i],
                        "cosine": (scores[i] * 1e4).round() / 1e4,
                    }));
                    match combine.as_str() {
                        "max" => fused[i] = fused[i].max(scores[i]),
                        "mean" => fused[i] += scores[i] / scopes.len() as f32,
                        _ => {}
                    }
                }
                rank_lists.push(rank_of);
            }
            if combine == "rrf" {
                fused = rrf_fuse(&rank_lists, n);
            }

            let order = argsort_desc(&fused);
            let results: Vec<_> = order
                .iter()
                .take(*top)
                .map(|&i| {
                    serde_json::json!({
                        "project": names[i],
                        "score": (fused[i] * 1e5).round() / 1e5,
                        "scopes": per_scope_detail[i],
                    })
                })
                .collect();
            if *json {
                println!(
                    "{}",
                    serde_json::json!({
                        "question": text, "plan": { "scopes": scopes, "query": query },
                        "combine": combine, "results": results,
                    })
                );
            } else {
                eprintln!("Q: {text}");
                for s in &scopes {
                    eprintln!("  lens: {s}");
                }
                for &i in order.iter().take(*top) {
                    println!("  {:.4}  {}", fused[i], names[i]);
                }
            }
            eprintln!("cache: {} hit / {} miss", cache.hits, cache.misses);
        }
    }
    Ok(())
}
