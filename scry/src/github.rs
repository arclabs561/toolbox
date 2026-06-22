//! GitHub corpus source.
//!
//! Fetches a user's public repositories and builds the same [`Project`] corpus
//! the local scanner produces, so all the embedding / clustering / retrieval
//! machinery works unchanged. Each project's text is the repo description plus
//! topics (the dense signal) followed by the README. There is no local source
//! tree, so only the `readme` surface applies.

use crate::corpus::Project;
use anyhow::{Context, Result};
use base64::Engine;
use futures::stream::{self, StreamExt};
use serde::Deserialize;

const README_CONCURRENCY: usize = 8;
const CHAR_BUDGET: usize = 24_000;

#[derive(Deserialize)]
struct Repo {
    name: String,
    description: Option<String>,
    fork: bool,
    #[serde(default)]
    topics: Vec<String>,
    #[serde(default)]
    archived: bool,
}

#[derive(Deserialize)]
struct ReadmeResp {
    content: String,
}

fn client() -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .user_agent("scry")
        .build()
        .context("build github http client")
}

/// Auth token: `GITHUB_TOKEN` env, else `gh auth token` (the user's keyring
/// credential). Lifts the rate limit from 60/hr to 5000/hr.
fn token() -> Option<String> {
    if let Ok(t) = std::env::var("GITHUB_TOKEN") {
        if !t.is_empty() {
            return Some(t);
        }
    }
    let out = std::process::Command::new("gh")
        .args(["auth", "token"])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let t = String::from_utf8(out.stdout).ok()?.trim().to_string();
    (!t.is_empty()).then_some(t)
}

fn cache_path(user: &str) -> std::path::PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    // Sanitize the username for the filename (it is the only variable component).
    let safe: String = user
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect();
    std::path::Path::new(&home).join(format!(".cache/scry/github/{safe}.json"))
}

/// Fetch a user's owned, non-archived public repos as projects. Forks are
/// excluded unless `include_forks`. The fetched corpus is cached on disk per
/// user so repeated runs (cluster, then query, then ask) don't re-hit the API;
/// pass `refresh` to bust it.
pub async fn fetch_user(user: &str, include_forks: bool, refresh: bool) -> Result<Vec<Project>> {
    let cp = cache_path(user);
    if !refresh {
        if let Ok(bytes) = std::fs::read(&cp) {
            if let Ok(projects) = serde_json::from_slice::<Vec<Project>>(&bytes) {
                eprintln!(
                    "github: {} cached repos for {user} (pass --refresh to refetch)",
                    projects.len()
                );
                return Ok(projects);
            }
        }
    }
    let token = token();
    let http = client()?;

    // Page through the repo list (100/page) until a short page.
    let mut repos: Vec<Repo> = Vec::new();
    for page in 1..=10 {
        let url = format!(
            "https://api.github.com/users/{user}/repos?per_page=100&page={page}&type=owner&sort=updated"
        );
        let mut req = http
            .get(&url)
            .header("Accept", "application/vnd.github+json");
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        let resp = req.send().await.context("list repos")?;
        let resp = resp
            .error_for_status()
            .context("github repo list (rate limit? bad user?)")?;
        let batch: Vec<Repo> = resp.json().await.context("decode repo list")?;
        let n = batch.len();
        repos.extend(batch);
        if n < 100 {
            break;
        }
    }
    repos.retain(|r| !r.archived && (include_forks || !r.fork));
    if repos.is_empty() {
        anyhow::bail!("no repos found for user {user:?} (private, empty, or all forks/archived)");
    }
    eprintln!(
        "github: {} repos for {user} (fetching READMEs, concurrency {README_CONCURRENCY})",
        repos.len()
    );

    // Fetch READMEs concurrently; a repo with none still contributes its metadata.
    let token = &token;
    let http = &http;
    let projects: Vec<Project> = stream::iter(repos.iter())
        .map(|r| async move {
            let readme = fetch_readme(http, user, &r.name, token.as_deref())
                .await
                .unwrap_or_default();
            let mut meta: Vec<String> = Vec::new();
            if let Some(d) = &r.description {
                if !d.trim().is_empty() {
                    meta.push(d.trim().to_string());
                }
            }
            if !r.topics.is_empty() {
                meta.push(format!("topics: {}", r.topics.join(", ")));
            }
            let meta = meta.join(". ");
            let body = match (meta.is_empty(), readme.trim().is_empty()) {
                (true, true) => return None, // nothing to embed
                (false, true) => meta,
                (true, false) => readme,
                (false, false) => format!("{meta}\n\n{readme}"),
            };
            let truncated: String = body.chars().take(CHAR_BUDGET).collect();
            Some(Project {
                name: r.name.clone(),
                dir: std::path::PathBuf::new(), // no local tree; code surface n/a
                readme: truncated,
            })
        })
        .buffered(README_CONCURRENCY)
        .filter_map(|p| async move { p })
        .collect()
        .await;

    if let Some(dir) = cp.parent() {
        std::fs::create_dir_all(dir).ok();
    }
    if let Ok(bytes) = serde_json::to_vec(&projects) {
        std::fs::write(&cp, bytes).ok();
    }
    Ok(projects)
}

async fn fetch_readme(
    http: &reqwest::Client,
    user: &str,
    repo: &str,
    token: Option<&str>,
) -> Option<String> {
    let url = format!("https://api.github.com/repos/{user}/{repo}/readme");
    let mut req = http
        .get(&url)
        .header("Accept", "application/vnd.github+json");
    if let Some(t) = token {
        req = req.bearer_auth(t);
    }
    let resp = req.send().await.ok()?;
    if !resp.status().is_success() {
        return None; // no README (404) or rate-limited
    }
    let r: ReadmeResp = resp.json().await.ok()?;
    let raw = r.content.replace(['\n', '\r'], "");
    let bytes = base64::engine::general_purpose::STANDARD.decode(raw).ok()?;
    String::from_utf8(bytes).ok()
}
