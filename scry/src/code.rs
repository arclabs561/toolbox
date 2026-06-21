//! Source-code gathering for the `code` surface.
//!
//! Walks a project directory, collects source files by extension, and splits
//! them into bounded character chunks. Per-project caps keep the embedding cost
//! finite — a project with thousands of files contributes at most
//! [`MAX_CHUNKS`] chunks, and the caller is told when that cap clipped a project.

use std::path::Path;

const CODE_EXTS: &[&str] = &[
    "rs", "py", "js", "ts", "tsx", "jsx", "go", "c", "h", "cpp", "cc", "hpp", "java", "rb",
    "scala", "swift", "kt", "ml", "hs", "jl", "lua", "sh", "sql", "ex", "exs", "clj", "zig",
];
const SKIP_DIRS: &[&str] = &[
    "target",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".cache",
    "vendor",
];
const MAX_CHUNK_CHARS: usize = 2000;
/// Per-project chunk cap. Bounds cost; projects exceeding it report `capped`.
pub const MAX_CHUNKS: usize = 48;

/// Gather up to [`MAX_CHUNKS`] source chunks for one project directory.
///
/// Returns the chunks and whether the cap clipped this project (so the caller
/// can report it rather than silently truncating).
pub fn gather_chunks(dir: &Path) -> (Vec<String>, bool) {
    let mut files = Vec::new();
    collect_files(dir, &mut files);
    files.sort();

    let mut chunks = Vec::new();
    let mut capped = false;
    for f in files {
        if chunks.len() >= MAX_CHUNKS {
            capped = true;
            break;
        }
        let Ok(text) = std::fs::read_to_string(&f) else {
            continue;
        };
        for chunk in chunk_chars(&text, MAX_CHUNK_CHARS) {
            if chunks.len() >= MAX_CHUNKS {
                capped = true;
                break;
            }
            chunks.push(chunk);
        }
    }
    (chunks, capped)
}

fn collect_files(dir: &Path, out: &mut Vec<std::path::PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.filter_map(|e| e.ok()) {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().into_owned();
        if path.is_dir() {
            if SKIP_DIRS.contains(&name.as_str()) || name.starts_with('.') {
                continue;
            }
            collect_files(&path, out);
        } else if path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| CODE_EXTS.contains(&e))
        {
            out.push(path);
        }
    }
}

/// Split text into chunks of at most `max` characters, on char boundaries.
fn chunk_chars(text: &str, max: usize) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    let chars: Vec<char> = trimmed.chars().collect();
    chars.chunks(max).map(|c| c.iter().collect()).collect()
}
