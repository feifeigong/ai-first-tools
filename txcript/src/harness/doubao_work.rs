//! ByteDance 豆包工作 local agent trajectories.
//!
//! A local-computer task writes
//! `%LOCALAPPDATA%/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.sessions/<id>/agents/<agent>/system/trajectory.jsonl`.
//! Each line is `{"role","content"}` with `content` a string. This is the
//! agent trajectory on disk. The desktop chat list is not documented as
//! reading that file back, so a written trajectory is a native file the
//! tool can list and convert, not a guarantee the 豆包工作 window opens it.

use std::fs;
use std::path::PathBuf;

use chrono::Utc;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::common::{Block, Message, Meta, Role};
use crate::error::{Error, Result};
use crate::harness::jsonl;
use crate::transcript::{Codec, Common, Discovered, Harness, Saved, Store, TextCodec, Transcript};

/// 豆包工作 harness marker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DoubaoWork;

impl Harness for DoubaoWork {
    const NAME: &'static str = "doubao_work";
    type Body = Vec<Value>;
}

impl Codec for DoubaoWork {
    fn to_common(transcript: &Transcript<Self>) -> Result<Transcript<Common>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            records_to_messages(&transcript.body),
        ))
    }

    fn from_common(transcript: &Transcript<Common>) -> Result<Transcript<Self>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            messages_to_records(&transcript.body),
        ))
    }
}

impl TextCodec for DoubaoWork {
    fn from_text(text: &str) -> Result<Transcript<Self>> {
        let records = jsonl::parse::<Value>(text);
        Ok(Transcript::new(meta_from_records(&records), records))
    }

    fn to_text(transcript: &Transcript<Self>) -> Result<String> {
        jsonl::render(&transcript.body)
    }
}

/// The `.doubaowork/agent_mode/workspace` directory.
#[derive(Debug, Clone)]
pub struct DoubaoWorkStore {
    pub workspace: PathBuf,
}

impl DoubaoWorkStore {
    pub fn new(workspace: impl Into<PathBuf>) -> Self {
        Self {
            workspace: workspace.into(),
        }
    }

    /// `DOUBAO_WORK_DIR`, otherwise the default DoubaoWork user-data workspace.
    #[must_use]
    pub fn default_root() -> Option<Self> {
        if let Ok(dir) = std::env::var("DOUBAO_WORK_DIR") {
            if !dir.is_empty() {
                return Some(Self::new(dir));
            }
        }
        let local = std::env::var_os("LOCALAPPDATA")?;
        Some(Self::new(
            PathBuf::from(local)
                .join("DoubaoWork")
                .join("User Data")
                .join("Default")
                .join(".doubaowork")
                .join("agent_mode")
                .join("workspace"),
        ))
    }
}

impl Store for DoubaoWorkStore {
    type H = DoubaoWork;
    type Ref = PathBuf;

    fn discover(&self) -> Result<Vec<Discovered<PathBuf>>> {
        let sessions = self.workspace.join(".sessions");
        let mut found = Vec::new();
        let Ok(sessions) = fs::read_dir(sessions) else {
            return Ok(found);
        };
        for session in sessions.flatten() {
            let agents = session.path().join("agents");
            let Ok(agents) = fs::read_dir(agents) else {
                continue;
            };
            for agent in agents.flatten() {
                let path = agent.path().join("system").join("trajectory.jsonl");
                if !path.is_file() {
                    continue;
                }
                let text = fs::read_to_string(&path).unwrap_or_default();
                let records = jsonl::parse::<Value>(&text);
                if records.is_empty() {
                    continue;
                }
                let mut meta = meta_from_records(&records);
                if let Some(id) = session.file_name().to_str() {
                    meta.id = id.to_string();
                }
                meta = saved_meta(&path, meta);
                found.push(Discovered { meta, reference: path });
            }
        }
        Ok(found)
    }

    fn load(&self, reference: &PathBuf) -> Result<Transcript<DoubaoWork>> {
        let text = fs::read_to_string(reference).map_err(|e| Error::Malformed {
            harness: DoubaoWork::NAME,
            detail: format!("reading {}: {e}", reference.display()),
        })?;
        let mut transcript = DoubaoWork::from_text(&text)?;
        if transcript.meta.id.is_empty() {
            if let Some(id) = session_id_from_path(reference) {
                transcript.meta.id = id;
            }
        }
        transcript.meta = saved_meta(reference, transcript.meta);
        Ok(transcript)
    }

    fn save(&self, transcript: &Transcript<DoubaoWork>) -> Result<Saved<PathBuf>> {
        let id = if transcript.meta.id.is_empty() {
            Uuid::new_v4().to_string()
        } else {
            transcript.meta.id.clone()
        };
        crate::harness::checked_id_component(DoubaoWork::NAME, &id)?;
        let path = self
            .workspace
            .join(".sessions")
            .join(&id)
            .join("agents")
            .join("txcript")
            .join("system")
            .join("trajectory.jsonl");
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| Error::Malformed {
                harness: DoubaoWork::NAME,
                detail: format!("creating {}: {e}", parent.display()),
            })?;
        }
        fs::write(&path, DoubaoWork::to_text(transcript)?).map_err(|e| Error::Malformed {
            harness: DoubaoWork::NAME,
            detail: format!("writing {}: {e}", path.display()),
        })?;
        let mut meta = transcript.meta.clone();
        meta.id = id.clone();
        fs::write(path.with_extension("txcript.json"), serde_json::to_vec(&meta)?)?;
        Ok(Saved { id, reference: path })
    }

    fn delete(&self, reference: &PathBuf) -> Result<()> {
        fs::remove_file(reference).map_err(|e| Error::Malformed {
            harness: DoubaoWork::NAME,
            detail: format!("removing {}: {e}", reference.display()),
        })
    }
}

fn saved_meta(path: &std::path::Path, fallback: Meta) -> Meta {
    fs::read(path.with_extension("txcript.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Meta>(&bytes).ok())
        .filter(|meta| session_id_from_path(path).as_deref() == Some(meta.id.as_str()))
        .unwrap_or(fallback)
}

fn records_to_messages(records: &[Value]) -> Vec<Message> {
    records
        .iter()
        .filter_map(|record| {
            let role = match record.get("role").and_then(Value::as_str) {
                Some("assistant") => Role::Assistant,
                Some("user") => Role::User,
                _ => return None,
            };
            let text = record.get("content").and_then(Value::as_str).unwrap_or("").trim();
            if text.is_empty() {
                return None;
            }
            Some(Message {
                role,
                content: vec![Block::Text { text: text.to_string() }],
                timestamp: Utc::now(),
                model: None,
                stop_reason: None,
                usage: None,
            })
        })
        .collect()
}

fn messages_to_records(messages: &[Message]) -> Vec<Value> {
    messages
        .iter()
        .filter_map(|message| {
            let text = message
                .content
                .iter()
                .filter_map(|block| match block {
                    Block::Text { text } => Some(text.as_str()),
                    Block::Thinking { text, .. } => Some(text.as_str()),
                    _ => None,
                })
                .collect::<Vec<_>>()
                .join("\n");
            if text.is_empty() {
                return None;
            }
            let role = if message.role == Role::Assistant { "assistant" } else { "user" };
            Some(json!({"role": role, "content": text}))
        })
        .collect()
}

fn session_id_from_path(path: &std::path::Path) -> Option<String> {
    let mut cursor = path.parent();
    while let Some(dir) = cursor {
        let parent_name = dir.parent().and_then(|p| p.file_name()).and_then(|n| n.to_str());
        if parent_name == Some(".sessions") {
            return dir.file_name().and_then(|n| n.to_str()).map(str::to_string);
        }
        cursor = dir.parent();
    }
    None
}

fn meta_from_records(records: &[Value]) -> Meta {
    let title = records.iter().find_map(|r| {
        if r.get("role").and_then(Value::as_str) == Some("user") {
            r.get("content").and_then(Value::as_str).map(|s| {
                let s = s.trim();
                s.chars().take(40).collect::<String>()
            })
        } else {
            None
        }
    });
    Meta {
        id: String::new(),
        timestamp: Utc::now(),
        cwd: None,
        git_branch: None,
        title,
        cli_version: None,
        model: None,
        lineage: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_role_content() {
        let text = "{\"role\":\"user\",\"content\":\"做一份周报\"}\n{\"role\":\"assistant\",\"content\":\"好的\"}\n";
        let parsed = DoubaoWork::from_text(text).unwrap();
        let common = DoubaoWork::to_common(&parsed).unwrap();
        assert_eq!(common.body.len(), 2);
        assert_eq!(common.body[0].content, vec![Block::Text { text: "做一份周报".into() }]);
    }

    #[test]
    fn save_and_load_roundtrip_in_temp_dir() {
        let root = std::env::temp_dir().join(format!("txcript-db-{}", Uuid::new_v4()));
        let store = DoubaoWorkStore::new(&root);
        let native = DoubaoWork::from_text(
            "{\"role\":\"user\",\"content\":\"做一份周报\"}\n{\"role\":\"assistant\",\"content\":\"好的\"}\n",
        )
        .unwrap();
        let mut common = DoubaoWork::to_common(&native).unwrap();
        common.meta.title = Some("迁移标题".into());
        common.meta.cwd = Some("D:\\目标目录".into());
        let saved = store.save(&DoubaoWork::from_common(&common).unwrap()).unwrap();
        let back = DoubaoWork::to_common(&store.load(&saved.reference).unwrap()).unwrap();
        assert_eq!(back.body.len(), 2);
        assert_eq!(back.meta.title, common.meta.title);
        assert_eq!(back.meta.cwd, common.meta.cwd);
        assert_eq!(store.discover().unwrap()[0].meta.cwd, common.meta.cwd);
        let mut invalid = common.meta.clone();
        invalid.id = "another-session".into();
        fs::write(saved.reference.with_extension("txcript.json"), serde_json::to_vec(&invalid).unwrap()).unwrap();
        assert_eq!(store.load(&saved.reference).unwrap().meta.cwd, None);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn live_install_parses() {
        let Some(store) = DoubaoWorkStore::default_root() else {
            return;
        };
        let found = store.discover().unwrap();
        if found.is_empty() {
            return;
        }
        let common = DoubaoWork::to_common(&store.load(&found[0].reference).unwrap()).unwrap();
        assert!(!common.body.is_empty());
    }
}
