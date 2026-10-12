//! Alibaba 千问办公 (QwenWork) sessions.
//!
//! Project transcripts live at
//! `~/.qwenworkcn/projects/<path-slug>/<session-id>.jsonl`. Records use the
//! same user/assistant JSONL shape observed on a local QwenWork install:
//! `type` is `user` or `assistant`, and `message.content` holds text,
//! thinking, tool_use, and tool_result parts.

use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::common::{Block, Message, Meta, Role, Tool, ToolOutput};
use crate::error::{Error, Result};
use crate::harness::jsonl;
use crate::transcript::{Codec, Common, Discovered, Harness, Saved, Store, TextCodec, Transcript};

/// 千问办公 harness marker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QwenWork;

impl Harness for QwenWork {
    const NAME: &'static str = "qwen_work";
    type Body = Vec<Value>;
}

impl Codec for QwenWork {
    fn to_common(transcript: &Transcript<Self>) -> Result<Transcript<Common>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            records_to_messages(&transcript.body),
        ))
    }

    fn from_common(transcript: &Transcript<Common>) -> Result<Transcript<Self>> {
        Ok(Transcript::new(
            transcript.meta.clone(),
            messages_to_records(&transcript.meta, &transcript.body),
        ))
    }
}

impl TextCodec for QwenWork {
    fn from_text(text: &str) -> Result<Transcript<Self>> {
        let records = jsonl::parse::<Value>(text);
        Ok(Transcript::new(meta_from_records(&records), records))
    }

    fn to_text(transcript: &Transcript<Self>) -> Result<String> {
        jsonl::render(&transcript.body)
    }
}

/// Reads and writes `~/.qwenworkcn`.
#[derive(Debug, Clone)]
pub struct QwenWorkStore {
    pub root: PathBuf,
}

impl QwenWorkStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// `QWENWORK_DIR`, otherwise `~/.qwenworkcn`.
    #[must_use]
    pub fn default_root() -> Option<Self> {
        if let Ok(dir) = std::env::var("QWENWORK_DIR") {
            if !dir.is_empty() {
                return Some(Self::new(dir));
            }
        }
        Some(Self::new(crate::harness::home_dir()?.join(".qwenworkcn")))
    }
}

impl Store for QwenWorkStore {
    type H = QwenWork;
    type Ref = PathBuf;

    fn discover(&self) -> Result<Vec<Discovered<PathBuf>>> {
        let projects = self.root.join("projects");
        let mut found = Vec::new();
        let Ok(projects) = fs::read_dir(projects) else {
            return Ok(found);
        };
        for project in projects.flatten() {
            let dir = project.path();
            if !dir.is_dir() {
                continue;
            }
            let Ok(files) = fs::read_dir(&dir) else {
                continue;
            };
            for file in files.flatten() {
                let path = file.path();
                if path.extension().and_then(|e| e.to_str()) != Some("jsonl") {
                    continue;
                }
                let text = fs::read_to_string(&path).unwrap_or_default();
                let records = jsonl::parse::<Value>(&text);
                if records.is_empty() {
                    continue;
                }
                found.push(Discovered {
                    meta: saved_meta(&path, meta_from_records(&records)),
                    reference: path,
                });
            }
        }
        Ok(found)
    }

    fn load(&self, reference: &PathBuf) -> Result<Transcript<QwenWork>> {
        let text = fs::read_to_string(reference).map_err(|e| Error::Malformed {
            harness: QwenWork::NAME,
            detail: format!("reading {}: {e}", reference.display()),
        })?;
        let mut transcript = QwenWork::from_text(&text)?;
        if transcript.meta.id.is_empty() {
            if let Some(id) = reference.file_stem().and_then(|n| n.to_str()) {
                transcript.meta.id = id.to_string();
            }
        }
        transcript.meta = saved_meta(reference, transcript.meta);
        Ok(transcript)
    }

    fn save(&self, transcript: &Transcript<QwenWork>) -> Result<Saved<PathBuf>> {
        let id = if transcript.meta.id.is_empty() {
            Uuid::new_v4().to_string()
        } else {
            transcript.meta.id.clone()
        };
        crate::harness::checked_id_component(QwenWork::NAME, &id)?;
        let cwd = transcript.meta.cwd.clone().unwrap_or_default();
        let dir = self.root.join("projects").join(path_slug(&cwd));
        fs::create_dir_all(&dir).map_err(|e| Error::Malformed {
            harness: QwenWork::NAME,
            detail: format!("creating {}: {e}", dir.display()),
        })?;
        let path = dir.join(format!("{id}.jsonl"));
        fs::write(&path, QwenWork::to_text(transcript)?).map_err(|e| Error::Malformed {
            harness: QwenWork::NAME,
            detail: format!("writing {}: {e}", path.display()),
        })?;
        let mut meta = transcript.meta.clone();
        meta.id = id.clone();
        fs::write(path.with_extension("txcript.json"), serde_json::to_vec(&meta)?)?;
        Ok(Saved { id, reference: path })
    }

    fn delete(&self, reference: &PathBuf) -> Result<()> {
        fs::remove_file(reference).map_err(|e| Error::Malformed {
            harness: QwenWork::NAME,
            detail: format!("removing {}: {e}", reference.display()),
        })
    }
}

fn saved_meta(path: &std::path::Path, fallback: Meta) -> Meta {
    fs::read(path.with_extension("txcript.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Meta>(&bytes).ok())
        .filter(|meta| Some(meta.id.as_str()) == path.file_stem().and_then(|name| name.to_str()))
        .unwrap_or(fallback)
}

fn records_to_messages(records: &[Value]) -> Vec<Message> {
    let mut out = Vec::new();
    for record in records {
        let kind = record.get("type").and_then(Value::as_str).unwrap_or("");
        if kind != "user" && kind != "assistant" {
            continue;
        }
        let message = record.get("message").cloned().unwrap_or(Value::Null);
        let role = if kind == "assistant" {
            Role::Assistant
        } else {
            Role::User
        };
        let content = parts_to_blocks(message.get("content"));
        if content.is_empty() {
            continue;
        }
        let timestamp = record
            .get("timestamp")
            .and_then(Value::as_str)
            .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
            .map(|t| t.with_timezone(&Utc))
            .unwrap_or_else(Utc::now);
        out.push(Message {
            role,
            content,
            timestamp,
            model: message
                .get("model")
                .and_then(Value::as_str)
                .map(str::to_string),
            stop_reason: None,
            usage: None,
        });
    }
    out
}

fn parts_to_blocks(content: Option<&Value>) -> Vec<Block> {
    let Some(content) = content else {
        return Vec::new();
    };
    if let Some(text) = content.as_str() {
        return vec![Block::Text { text: text.to_string() }];
    }
    let Some(parts) = content.as_array() else {
        return Vec::new();
    };
    let mut blocks = Vec::new();
    for part in parts {
        match part.get("type").and_then(Value::as_str) {
            Some("text") => {
                if let Some(text) = part.get("text").and_then(Value::as_str) {
                    if !text.is_empty() {
                        blocks.push(Block::Text { text: text.to_string() });
                    }
                }
            }
            Some("thinking") => {
                if let Some(text) = part.get("thinking").and_then(Value::as_str) {
                    blocks.push(Block::Thinking {
                        text: text.to_string(),
                        signature: part
                            .get("signature")
                            .and_then(Value::as_str)
                            .map(str::to_string),
                        encrypted: None,
                    });
                }
            }
            Some("tool_use") => {
                let id = part.get("id").and_then(Value::as_str).unwrap_or("tool").to_string();
                let name = part.get("name").and_then(Value::as_str).unwrap_or("tool");
                let input = part.get("input").cloned().unwrap_or(Value::Null);
                blocks.push(Block::ToolUse {
                    id,
                    tool: Tool::from_canonical(name, input),
                });
            }
            Some("tool_result") => {
                let id = part
                    .get("tool_use_id")
                    .and_then(Value::as_str)
                    .unwrap_or("tool")
                    .to_string();
                let output = match part.get("content") {
                    Some(Value::String(s)) => ToolOutput::Text(s.clone()),
                    Some(other) => ToolOutput::Json(other.clone()),
                    None => ToolOutput::Text(String::new()),
                };
                blocks.push(Block::ToolResult {
                    tool_use_id: id,
                    content: output,
                    is_error: part.get("is_error").and_then(Value::as_bool).unwrap_or(false),
                });
            }
            _ => {}
        }
    }
    blocks
}

fn messages_to_records(meta: &Meta, messages: &[Message]) -> Vec<Value> {
    let session_id = if meta.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        meta.id.clone()
    };
    let cwd = meta.cwd.clone().unwrap_or_default();
    let mut records = Vec::new();
    let mut parent: Option<String> = None;
    for message in messages {
        let uuid = Uuid::new_v4().to_string();
        let kind = if message.role == Role::Assistant { "assistant" } else { "user" };
        let parts: Vec<Value> = message
            .content
            .iter()
            .filter_map(|block| match block {
                Block::Text { text } => Some(json!({"type": "text", "text": text})),
                Block::Thinking { text, signature, .. } => Some(json!({
                    "type": "thinking",
                    "thinking": text,
                    "signature": signature,
                })),
                Block::ToolUse { id, tool } => {
                    let (name, input) = tool.to_canonical();
                    Some(json!({"type": "tool_use", "id": id, "name": name, "input": input}))
                }
                Block::ToolResult { tool_use_id, content, is_error } => {
                    let body = match content {
                        ToolOutput::Text(s) => Value::String(s.clone()),
                        ToolOutput::Json(v) => v.clone(),
                    };
                    Some(json!({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": body,
                        "is_error": is_error,
                    }))
                }
                _ => None,
            })
            .collect();
        if parts.is_empty() {
            continue;
        }
        let mut record = json!({
            "type": kind,
            "uuid": uuid,
            "parentUuid": parent,
            "sessionId": session_id,
            "cwd": cwd,
            "timestamp": message.timestamp.to_rfc3339(),
            "message": { "role": kind, "content": parts },
        });
        parent = Some(uuid);
        if let Some(obj) = record.as_object_mut() {
            if obj.get("parentUuid").and_then(Value::as_null).is_some() {
                obj.insert("parentUuid".into(), Value::Null);
            }
        }
        records.push(record);
    }
    records
}

fn meta_from_records(records: &[Value]) -> Meta {
    let id = records
        .iter()
        .find_map(|r| r.get("sessionId").and_then(Value::as_str))
        .unwrap_or("")
        .to_string();
    let cwd = records
        .iter()
        .find_map(|r| r.get("cwd").and_then(Value::as_str))
        .map(str::to_string);
    let timestamp = records
        .iter()
        .find_map(|r| {
            r.get("timestamp")
                .and_then(Value::as_str)
                .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
                .map(|t| t.with_timezone(&Utc))
        })
        .unwrap_or_else(Utc::now);
    Meta {
        id,
        timestamp,
        cwd,
        git_branch: None,
        title: None,
        cli_version: None,
        model: None,
        lineage: None,
    }
}

/// QwenWork project folders replace every non-ASCII-alphanumeric character with `-`.
fn path_slug(cwd: &str) -> String {
    let slug: String = cwd
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect();
    if slug.is_empty() { "unknown".into() } else { slug }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_text_turn() {
        let text = r#"{"type":"user","sessionId":"q1","cwd":"D:\\proj","timestamp":"2026-08-13T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"你好"}]}}
{"type":"assistant","sessionId":"q1","timestamp":"2026-08-13T10:00:02Z","message":{"role":"assistant","content":[{"type":"text","text":"在"}]}}
"#;
        let parsed = QwenWork::from_text(text).unwrap();
        let common = QwenWork::to_common(&parsed).unwrap();
        assert_eq!(common.meta.id, "q1");
        assert_eq!(common.body.len(), 2);
        assert_eq!(
            common.body[0].content,
            vec![Block::Text { text: "你好".into() }]
        );
    }

    #[test]
    fn save_and_load_roundtrip_in_temp_dir() {
        let root = std::env::temp_dir().join(format!("txcript-qw-{}", Uuid::new_v4()));
        let store = QwenWorkStore::new(&root);
        let native = QwenWork::from_text(
            r#"{"type":"user","sessionId":"q1","cwd":"D:\\proj","timestamp":"2026-08-13T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"你好"}]}}
{"type":"assistant","sessionId":"q1","cwd":"D:\\proj","timestamp":"2026-08-13T10:00:02Z","message":{"role":"assistant","content":[{"type":"text","text":"在"}]}}
"#,
        )
        .unwrap();
        let mut common = QwenWork::to_common(&native).unwrap();
        common.meta.title = Some("迁移标题".into());
        let saved = store.save(&QwenWork::from_common(&common).unwrap()).unwrap();
        let back = QwenWork::to_common(&store.load(&saved.reference).unwrap()).unwrap();
        assert_eq!(back.body.len(), 2);
        assert_eq!(back.meta.title, common.meta.title);
        assert_eq!(back.meta.cwd, common.meta.cwd);
        assert_eq!(store.discover().unwrap()[0].meta.title, common.meta.title);
        let mut invalid = common.meta.clone();
        invalid.id = "another-session".into();
        fs::write(saved.reference.with_extension("txcript.json"), serde_json::to_vec(&invalid).unwrap()).unwrap();
        assert_eq!(store.load(&saved.reference).unwrap().meta.title, None);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn live_install_parses() {
        let Some(store) = QwenWorkStore::default_root() else {
            return;
        };
        let found = store.discover().unwrap();
        if found.is_empty() {
            return;
        }
        let native = store.load(&found[0].reference).unwrap();
        let common = QwenWork::to_common(&native).unwrap();
        assert!(!common.body.is_empty());
    }
}
