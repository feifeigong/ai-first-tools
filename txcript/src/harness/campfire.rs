//! Campfire embeds pi and writes the identical on-disk format under
//! `~/.campfire/agent/sessions/` (honoring `CAMPFIRE_CODING_AGENT_*`). It is a
//! thin delegate: the body type, codec, and store logic are pi's, reused
//! verbatim; only the harness identity and the sessions root differ.

use std::path::PathBuf;

use crate::error::{Error, Result};
use crate::harness::jsonl;
use crate::harness::pi::{self, Record};
use crate::transcript::{Codec, Common, Discovered, Harness, Saved, Store, TextCodec, Transcript};

/// The Campfire harness marker. Shares pi's native [`Record`] body.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Campfire;

impl Harness for Campfire {
    const NAME: &'static str = "campfire";
    type Body = Vec<Record>;
}

impl Codec for Campfire {
    fn to_common(transcript: &Transcript<Self>) -> Result<Transcript<Common>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            pi::records_to_messages(&transcript.body, transcript.meta.timestamp),
        ))
    }

    fn from_common(transcript: &Transcript<Common>) -> Result<Transcript<Self>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            pi::messages_to_records(&transcript.meta, &transcript.body),
        ))
    }
}

impl TextCodec for Campfire {
    fn from_text(text: &str) -> Result<Transcript<Self>> {
        // Identical format to pi — reuse its parser and metadata extraction.
        let records = pi::records_from_text(text);
        Ok(Transcript::new(pi::meta_from_records(&records), records))
    }

    fn to_text(transcript: &Transcript<Self>) -> Result<String> {
        jsonl::render(&transcript.body)
    }
}

/// Reads and writes Campfire sessions under a sessions root.
#[derive(Debug, Clone)]
pub struct CampfireStore {
    pub sessions_dir: PathBuf,
}

impl CampfireStore {
    pub fn new(sessions_dir: impl Into<PathBuf>) -> Self {
        Self {
            sessions_dir: sessions_dir.into(),
        }
    }

    /// Campfire's default sessions root, honoring `CAMPFIRE_CODING_AGENT_*`.
    pub fn default_root() -> Option<Self> {
        pi::resolve_sessions_dir(".campfire", "CAMPFIRE").map(Self::new)
    }
}

impl Store for CampfireStore {
    type H = Campfire;
    type Ref = PathBuf;

    fn discover(&self) -> Result<Vec<Discovered<PathBuf>>> {
        Ok(pi::discover_format(&self.sessions_dir))
    }

    fn load(&self, reference: &PathBuf) -> Result<Transcript<Campfire>> {
        pi::load_session(reference, Campfire::from_text)
    }

    fn save(&self, transcript: &Transcript<Campfire>) -> Result<Saved<PathBuf>> {
        pi::write_session(&self.sessions_dir, &transcript.meta, &transcript.body)
    }

    /// Removes a Campfire session log. Guarded on shape and containment:
    /// the reference must be a `.jsonl` file resolving within `sessions_dir`,
    /// so a foreign or stale reference never removes files outside the sessions root.
    fn delete(&self, reference: &PathBuf) -> Result<()> {
        if reference.extension().is_none_or(|ext| ext != "jsonl") {
            return Err(Error::Malformed {
                harness: Campfire::NAME,
                detail: format!("not a campfire session file: {}", reference.display()),
            });
        }
        let canon = reference.canonicalize()?;
        let sessions = self.sessions_dir.canonicalize()?;
        if canon.strip_prefix(&sessions).is_err() || canon == sessions {
            return Err(Error::Malformed {
                harness: Campfire::NAME,
                detail: format!(
                    "refusing to delete outside the sessions root: {}",
                    reference.display()
                ),
            });
        }
        Ok(std::fs::remove_file(canon)?)
    }
}
