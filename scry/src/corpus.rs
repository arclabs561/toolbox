//! Project discovery and scope lenses.

use std::path::Path;

/// One project: its directory name, path, and (truncated) README text.
pub struct Project {
    pub name: String,
    pub dir: std::path::PathBuf,
    pub readme: String,
}

const CHAR_BUDGET: usize = 24_000;
const SKIP_NAMES: &[&str] = &["target", "node_modules", "scry"];

/// Named scope shorthands: `(name, instruction)`. The instruction is prepended
/// to text in Qwen3-Embedding's `Instruct: {task}\nQuery: {text}` form.
pub const DEFAULT_SCOPES: &[(&str, &str)] = &[
    ("purpose", "Represent this software project by its core purpose and the problem it solves."),
    ("techniques", "Represent this software project by the algorithms, methods, and technical techniques it uses."),
    ("domain", "Represent this software project by its subject domain and the field it belongs to."),
];

/// Discover projects: immediate subdirectories of `root` that contain a
/// `README*` file, skipping dotted/underscored names and build dirs.
pub fn discover(root: &Path) -> std::io::Result<Vec<Project>> {
    let mut out = Vec::new();
    let mut entries: Vec<_> = std::fs::read_dir(root)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let name = entry.file_name().to_string_lossy().into_owned();
        if SKIP_NAMES.contains(&name.as_str()) || name.starts_with('_') || name.starts_with('.') {
            continue;
        }
        let Some(readme) = find_readme(&entry.path()) else {
            continue;
        };
        let Ok(text) = std::fs::read_to_string(&readme) else {
            continue;
        };
        let text = text.trim();
        if text.is_empty() {
            continue;
        }
        let truncated: String = text.chars().take(CHAR_BUDGET).collect();
        out.push(Project {
            name,
            dir: entry.path(),
            readme: truncated,
        });
    }
    Ok(out)
}

fn find_readme(dir: &Path) -> Option<std::path::PathBuf> {
    let mut hits: Vec<_> = std::fs::read_dir(dir)
        .ok()?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| {
            p.is_file()
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.starts_with("README"))
        })
        .collect();
    hits.sort();
    hits.into_iter().next()
}

/// Format one input in the instruction-conditioned form.
pub fn format_input(instruction: &str, text: &str) -> String {
    format!("Instruct: {instruction}\nQuery: {text}")
}

/// Resolve a named scope to its instruction, or pass free text through.
pub fn resolve_scope(name_or_instruction: &str) -> String {
    DEFAULT_SCOPES
        .iter()
        .find(|(n, _)| *n == name_or_instruction)
        .map(|(_, instr)| instr.to_string())
        .unwrap_or_else(|| name_or_instruction.to_string())
}

/// The default project root: `~/Documents/dev`.
pub fn default_root() -> std::path::PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    Path::new(&home).join("Documents/dev")
}
