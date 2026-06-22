//! Disk-backed embedding cache.
//!
//! Keyed by SHA-256 of `(model, dimensions, exact input text)`. The scope
//! instruction is part of the input text, so changing the lens correctly
//! produces new embeddings while an unchanged README under a seen scope is
//! never re-embedded.

use anyhow::{Context, Result};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// In-memory map persisted to a JSON file, plus hit/miss counters for the run.
pub struct Cache {
    path: PathBuf,
    pub map: HashMap<String, Vec<f32>>,
    pub hits: usize,
    pub misses: usize,
}

impl Cache {
    /// Load the cache from `path` (empty if it does not exist or is corrupt).
    pub fn load(path: PathBuf) -> Self {
        let map = std::fs::read(&path)
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        Self {
            path,
            map,
            hits: 0,
            misses: 0,
        }
    }

    /// Cache key for one input. `provider` and `dimensions` are part of the key
    /// so different upstream providers and truncated/full-width embeddings never
    /// collide.
    pub fn key(model: &str, provider: Option<&str>, dimensions: Option<u32>, text: &str) -> String {
        let mut h = Sha256::new();
        h.update(model.as_bytes());
        h.update([0]);
        h.update(provider.unwrap_or("").as_bytes());
        h.update([0]);
        h.update(format!("{dimensions:?}").as_bytes());
        h.update([0]);
        h.update(text.as_bytes());
        format!("{:x}", h.finalize())
    }

    /// Persist the cache atomically (write to a temp file, then rename).
    pub fn save(&self) -> Result<()> {
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir).ok();
        }
        let tmp = self.path.with_extension("tmp");
        std::fs::write(&tmp, serde_json::to_vec(&self.map)?).context("write cache")?;
        std::fs::rename(&tmp, &self.path).context("commit cache")?;
        Ok(())
    }

    /// Default cache location: `~/.cache/scry/embeddings.json`.
    pub fn default_path() -> PathBuf {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
        Path::new(&home).join(".cache/scry/embeddings.json")
    }
}
