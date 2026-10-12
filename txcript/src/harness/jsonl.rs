//! Shared JSONL parse/render for line-based harnesses.

use std::borrow::Cow;
use std::path::Path;

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::error::Result;

/// The `type` tag alone — the cheapest classification of a line. Borrowed,
/// so probing tokenizes the line but allocates nothing; `Cow` still admits
/// an escaped tag.
#[derive(Deserialize)]
pub(crate) struct TypeProbe<'a> {
    #[serde(rename = "type", default, borrow)]
    pub kind: Option<Cow<'a, str>>,
}

/// Parse JSONL records, skipping blank and invalid lines.
pub(crate) fn parse<R: DeserializeOwned>(text: &str) -> Vec<R> {
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<R>(line).ok())
        .collect()
}

/// Render records as newline-terminated JSON, one object per line.
pub(crate) fn render<R: Serialize>(records: &[R]) -> Result<String> {
    let mut out = String::new();
    for record in records {
        out.push_str(&serde_json::to_string(record)?);
        out.push('\n');
    }
    Ok(out)
}

/// A session id derived from a file name (its stem) — the fallback a [`Store`]
/// uses when the session text carried no internal id.
///
/// [`Store`]: crate::Store
pub(crate) fn file_id(path: &Path) -> String {
    path.file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default()
}
