//! Tencent WorkBuddy sessions.
//!
//! The domestic app and the overseas WorkBuddy AI app use the same JSONL
//! shape, in two different home directories. Domestic transcripts live under
//! `~/.workbuddy/projects/<project-slug>/<session-id>.jsonl` (sidebar index
//! `~/.workbuddy/workbuddy.db`). WorkBuddy AI uses `~/.workbuddy-ai` with the
//! same layout. Field names below were taken from sessions on a real install
//! (message `input_text` / `output_text`, `function_call`,
//! `function_call_result`, `reasoning`, `ai-title`).

use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, TimeZone, Utc};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::common::{Block, Message, Meta, Role, Tool, ToolOutput};
use crate::error::{Error, Result};
use crate::harness::jsonl;
use crate::transcript::{Codec, Common, Discovered, Harness, Saved, Store, TextCodec, Transcript};

/// WorkBuddy harness marker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WorkBuddy;

impl Harness for WorkBuddy {
    const NAME: &'static str = "workbuddy";
    type Body = Vec<Value>;
}

impl Codec for WorkBuddy {
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

impl TextCodec for WorkBuddy {
    fn from_text(text: &str) -> Result<Transcript<Self>> {
        parse_jsonl(text)
    }

    fn to_text(transcript: &Transcript<Self>) -> Result<String> {
        jsonl::render(&transcript.body)
    }
}

/// Overseas WorkBuddy AI. Same records as [`WorkBuddy`], stored under
/// `~/.workbuddy-ai` instead of `~/.workbuddy`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WorkBuddyAi;

impl Harness for WorkBuddyAi {
    const NAME: &'static str = "workbuddy_ai";
    type Body = Vec<Value>;
}

impl Codec for WorkBuddyAi {
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

impl TextCodec for WorkBuddyAi {
    fn from_text(text: &str) -> Result<Transcript<Self>> {
        parse_jsonl(text)
    }

    fn to_text(transcript: &Transcript<Self>) -> Result<String> {
        jsonl::render(&transcript.body)
    }
}

fn parse_jsonl<H: Harness<Body = Vec<Value>>>(text: &str) -> Result<Transcript<H>> {
    let records = jsonl::parse::<Value>(text);
    Ok(Transcript::new(meta_from_records(&records), records))
}

/// Reads and writes WorkBuddy's `~/.workbuddy` tree.
#[derive(Debug, Clone)]
pub struct WorkBuddyStore {
    pub root: PathBuf,
}

impl WorkBuddyStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// `WORKBUDDY_DIR`, otherwise `~/.workbuddy`.
    #[must_use]
    pub fn default_root() -> Option<Self> {
        Some(Self::new(root_from_env("WORKBUDDY_DIR", ".workbuddy")?))
    }
}

impl Store for WorkBuddyStore {
    type H = WorkBuddy;
    type Ref = PathBuf;

    fn discover(&self) -> Result<Vec<Discovered<PathBuf>>> {
        discover_projects(&self.root)
    }

    fn load(&self, reference: &PathBuf) -> Result<Transcript<WorkBuddy>> {
        load_file(reference)
    }

    fn save(&self, transcript: &Transcript<WorkBuddy>) -> Result<Saved<PathBuf>> {
        save_file(&self.root, transcript)
    }

    fn delete(&self, reference: &PathBuf) -> Result<()> {
        delete_file(WorkBuddy::NAME, reference)
    }
}

/// Reads and writes WorkBuddy AI's `~/.workbuddy-ai` tree.
#[derive(Debug, Clone)]
pub struct WorkBuddyAiStore {
    pub root: PathBuf,
}

impl WorkBuddyAiStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// `WORKBUDDY_AI_DIR`, otherwise `~/.workbuddy-ai`.
    #[must_use]
    pub fn default_root() -> Option<Self> {
        Some(Self::new(root_from_env("WORKBUDDY_AI_DIR", ".workbuddy-ai")?))
    }
}

impl Store for WorkBuddyAiStore {
    type H = WorkBuddyAi;
    type Ref = PathBuf;

    fn discover(&self) -> Result<Vec<Discovered<PathBuf>>> {
        discover_projects(&self.root)
    }

    fn load(&self, reference: &PathBuf) -> Result<Transcript<WorkBuddyAi>> {
        load_file(reference)
    }

    fn save(&self, transcript: &Transcript<WorkBuddyAi>) -> Result<Saved<PathBuf>> {
        save_file(&self.root, transcript)
    }

    fn delete(&self, reference: &PathBuf) -> Result<()> {
        delete_file(WorkBuddyAi::NAME, reference)
    }
}

fn discover_projects(root: &std::path::Path) -> Result<Vec<Discovered<PathBuf>>> {
    let projects = root.join("projects");
    let mut found = Vec::new();
    let entries = match fs::read_dir(&projects) {
        Ok(entries) => entries,
        Err(_) => return Ok(found),
    };
    for project in entries.flatten() {
        let dir = project.path();
        if !dir.is_dir() {
            continue;
        }
        let files = match fs::read_dir(&dir) {
            Ok(files) => files,
            Err(_) => continue,
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
                meta: meta_from_records(&records),
                reference: path,
            });
        }
    }
    Ok(found)
}

fn load_file<H: TextCodec>(reference: &std::path::Path) -> Result<Transcript<H>> {
    let text = fs::read_to_string(reference).map_err(|e| Error::Malformed {
        harness: H::NAME,
        detail: format!("reading {}: {e}", reference.display()),
    })?;
    H::from_text(&text)
}

fn save_file<H: TextCodec>(
    root: &std::path::Path,
    transcript: &Transcript<H>,
) -> Result<Saved<PathBuf>> {
    let id = if transcript.meta.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        transcript.meta.id.clone()
    };
    crate::harness::checked_id_component(H::NAME, &id)?;
    let cwd = transcript.meta.cwd.clone().unwrap_or_else(|| {
        std::env::current_dir()
            .map(|p| p.display().to_string())
            .unwrap_or_default()
    });
    let dir = root.join("projects").join(project_slug(&cwd));
    fs::create_dir_all(&dir).map_err(|e| Error::Malformed {
        harness: H::NAME,
        detail: format!("creating {}: {e}", dir.display()),
    })?;
    let path = dir.join(format!("{id}.jsonl"));
    fs::write(&path, H::to_text(transcript)?).map_err(|e| Error::Malformed {
        harness: H::NAME,
        detail: format!("writing {}: {e}", path.display()),
    })?;
    index_session(
        root,
        &id,
        &cwd,
        transcript.meta.title.as_deref(),
        transcript.meta.timestamp,
    );
    Ok(Saved {
        id,
        reference: path,
    })
}

fn delete_file(harness: &'static str, reference: &std::path::Path) -> Result<()> {
    fs::remove_file(reference).map_err(|e| Error::Malformed {
        harness,
        detail: format!("removing {}: {e}", reference.display()),
    })
}

fn root_from_env(key: &str, folder: &str) -> Option<PathBuf> {
    if let Ok(dir) = std::env::var(key) {
        if !dir.is_empty() {
            return Some(PathBuf::from(dir));
        }
    }
    Some(crate::harness::home_dir()?.join(folder))
}

fn records_to_messages(records: &[Value]) -> Vec<Message> {
    let mut out = Vec::new();
    for record in records {
        let kind = record.get("type").and_then(Value::as_str).unwrap_or("");
        let timestamp = record_time(record);
        match kind {
            "message" => {
                let role = match record.get("role").and_then(Value::as_str) {
                    Some("assistant") => Role::Assistant,
                    _ => Role::User,
                };
                let text = blocks_text(record.get("content"));
                if role == Role::User {
                    let text = visible_user_text(&text);
                    if text.is_empty() {
                        continue;
                    }
                    out.push(Message {
                        role,
                        content: vec![Block::Text { text }],
                        timestamp,
                        model: None,
                        stop_reason: None,
                        usage: None,
                    });
                } else if !text.is_empty() {
                    out.push(Message {
                        role,
                        content: vec![Block::Text { text }],
                        timestamp,
                        model: None,
                        stop_reason: None,
                        usage: None,
                    });
                }
            }
            "reasoning" => {
                let text = blocks_text(record.get("content"));
                if text.is_empty() {
                    continue;
                }
                out.push(Message {
                    role: Role::Assistant,
                    content: vec![Block::Thinking {
                        text,
                        signature: None,
                        encrypted: None,
                    }],
                    timestamp,
                    model: None,
                    stop_reason: None,
                    usage: None,
                });
            }
            "function_call" => {
                let name = record.get("name").and_then(Value::as_str).unwrap_or("tool");
                let id = record
                    .get("callId")
                    .and_then(Value::as_str)
                    .unwrap_or("call")
                    .to_string();
                let input = record
                    .get("arguments")
                    .map(parse_arguments)
                    .unwrap_or(Value::Null);
                out.push(Message {
                    role: Role::Assistant,
                    content: vec![Block::ToolUse {
                        id,
                        tool: Tool::from_canonical(name, input),
                    }],
                    timestamp,
                    model: None,
                    stop_reason: None,
                    usage: None,
                });
            }
            "function_call_result" => {
                let id = record
                    .get("callId")
                    .and_then(Value::as_str)
                    .unwrap_or("call")
                    .to_string();
                let output = match record.get("output") {
                    Some(Value::String(s)) => ToolOutput::Text(s.clone()),
                    Some(other) => ToolOutput::Json(other.clone()),
                    None => ToolOutput::Text(String::new()),
                };
                let status = record.get("status").and_then(Value::as_str).unwrap_or("completed");
                let is_error = !matches!(status, "completed" | "success" | "ok");
                out.push(Message {
                    role: Role::User,
                    content: vec![Block::ToolResult {
                        tool_use_id: id,
                        content: output,
                        is_error,
                    }],
                    timestamp,
                    model: None,
                    stop_reason: None,
                    usage: None,
                });
            }
            _ => {}
        }
    }
    out
}

fn messages_to_records(meta: &Meta, messages: &[Message]) -> Vec<Value> {
    let session_id = if meta.id.is_empty() {
        Uuid::new_v4().to_string()
    } else {
        meta.id.clone()
    };
    let cwd = meta.cwd.clone().unwrap_or_default();
    let mut records = Vec::new();
    let mut prev: Option<String> = None;
    for message in messages {
        for block in &message.content {
            let id = Uuid::new_v4().to_string();
            let timestamp = message.timestamp.timestamp_millis();
            let mut record = match (message.role, block) {
                (Role::User, Block::Text { text }) => json!({
                    "type": "message",
                    "role": "user",
                    "content": [{ "type": "input_text", "text": format!("<user_query>\n{text}\n</user_query>") }],
                }),
                (Role::Assistant, Block::Text { text }) => json!({
                    "type": "message",
                    "role": "assistant",
                    "content": [{ "type": "output_text", "text": text }],
                }),
                (_, Block::Thinking { text, .. }) => json!({
                    "type": "reasoning",
                    "content": [{ "type": "text", "text": text }],
                }),
                (_, Block::ToolUse { id: call_id, tool }) => {
                    let (name, input) = tool.to_canonical();
                    json!({
                        "type": "function_call",
                        "name": name,
                        "callId": call_id,
                        "arguments": input.to_string(),
                    })
                }
                (_, Block::ToolResult { tool_use_id, content, is_error }) => {
                    let output = match content {
                        ToolOutput::Text(s) => Value::String(s.clone()),
                        ToolOutput::Json(v) => v.clone(),
                    };
                    json!({
                        "type": "function_call_result",
                        "callId": tool_use_id,
                        "output": output,
                        "status": if *is_error { "error" } else { "completed" },
                    })
                }
                _ => continue,
            };
            if let Some(obj) = record.as_object_mut() {
                obj.insert("id".into(), Value::String(id.clone()));
                obj.insert("sessionId".into(), Value::String(session_id.clone()));
                obj.insert("cwd".into(), Value::String(cwd.clone()));
                obj.insert("timestamp".into(), json!(timestamp));
                if let Some(parent) = &prev {
                    obj.insert("parentId".into(), Value::String(parent.clone()));
                }
            }
            prev = Some(id);
            records.push(record);
        }
    }
    if let Some(title) = &meta.title {
        records.push(json!({
            "type": "ai-title",
            "aiTitle": title,
            "sessionId": session_id,
            "cwd": cwd,
            "timestamp": meta.timestamp.timestamp_millis(),
        }));
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
    let title = records.iter().rev().find_map(|r| {
        if r.get("type").and_then(Value::as_str) == Some("ai-title") {
            r.get("aiTitle").and_then(Value::as_str).map(str::to_string)
        } else {
            None
        }
    });
    let timestamp = records.first().map(record_time).unwrap_or_else(Utc::now);
    Meta {
        id,
        timestamp,
        cwd,
        git_branch: None,
        title,
        cli_version: None,
        model: None,
        lineage: None,
    }
}

fn record_time(record: &Value) -> DateTime<Utc> {
    let ms = record.get("timestamp").and_then(Value::as_i64).unwrap_or(0);
    Utc.timestamp_millis_opt(ms).single().unwrap_or_else(Utc::now)
}

fn blocks_text(content: Option<&Value>) -> String {
    let Some(content) = content else {
        return String::new();
    };
    if let Some(text) = content.as_str() {
        return text.to_string();
    }
    let Some(items) = content.as_array() else {
        return String::new();
    };
    items
        .iter()
        .filter_map(|b| b.get("text").and_then(Value::as_str))
        .filter(|t| !t.is_empty())
        .collect::<Vec<_>>()
        .join("\n")
}

fn visible_user_text(raw: &str) -> String {
    if let Some(inner) = raw.trim().strip_prefix("<user_query>").and_then(|text| text.strip_suffix("</user_query>")) {
        return inner.trim().to_string();
    }
    if raw.trim_start().starts_with("<cb_summary>") {
        return String::new();
    }
    if let Some(start) = raw.rfind("<user_query>") {
        let rest = &raw[start + "<user_query>".len()..];
        if let Some(end) = rest.find("</user_query>") {
            return rest[..end].trim().to_string();
        }
    }
    raw.trim().to_string()
}

fn parse_arguments(value: &Value) -> Value {
    match value {
        Value::String(s) => serde_json::from_str(s).unwrap_or_else(|_| Value::String(s.clone())),
        other => other.clone(),
    }
}

/// `C:\Users\name\proj` -> `c-Users-name-proj`, matching WorkBuddy's project folders.
fn project_slug(cwd: &str) -> String {
    let mut out = String::new();
    for ch in cwd.chars() {
        if matches!(ch, '/' | '\\' | ':') {
            if !out.ends_with('-') {
                out.push('-');
            }
        } else {
            out.push(ch);
        }
    }
    let trimmed = out.trim_matches('-');
    let mut chars = trimmed.chars();
    match chars.next() {
        Some(c) if c.is_ascii_alphabetic() => {
            let mut s = c.to_ascii_lowercase().to_string();
            s.push_str(chars.as_str());
            s
        }
        Some(c) => {
            let mut s = String::new();
            s.push(c);
            s.push_str(chars.as_str());
            s
        }
        None => "unknown".into(),
    }
}

fn index_session(root: &std::path::Path, id: &str, cwd: &str, title: Option<&str>, started: DateTime<Utc>) {
    #[cfg(any(feature = "opencode", feature = "hermes"))]
    {
        let db = root.join("workbuddy.db");
        if !db.is_file() {
            return;
        }
        let Ok(conn) = rusqlite::Connection::open(&db) else {
            return;
        };
        let user_id: String = conn
            .query_row("SELECT user_id FROM sessions LIMIT 1", [], |row| row.get(0))
            .unwrap_or_else(|_| "local".into());
        let now = Utc::now().timestamp_millis();
        let created = started.timestamp_millis();
        // The app files a session under a Space when it is not a playground
        // task and its folder is a registered workspace; match that shape.
        let slashed = cwd.replace('\\', "/");
        let _ = conn.execute(
            "INSERT OR REPLACE INTO sessions (id, cwd, user_id, title, custom_title, status, created_at, updated_at, last_activity_at, is_playground, source_mode, mode, transport) VALUES (?1, ?2, ?3, ?4, ?4, 'completed', ?5, ?6, ?6, 0, 'craft', 'craft', 'local')",
            rusqlite::params![id, slashed, user_id, title.unwrap_or("Imported"), created, now],
        );
        let native = cwd.replace('/', "\\");
        let _ = conn.execute(
            "INSERT OR IGNORE INTO workspaces (path, last_opened_at) SELECT ?1, ?2 WHERE NOT EXISTS (SELECT 1 FROM workspaces WHERE lower(replace(path, '/', '\\')) = lower(?1))",
            rusqlite::params![native, now],
        );
    }
    #[cfg(not(any(feature = "opencode", feature = "hermes")))]
    {
        let _ = (root, id, cwd, title, started);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn imported_nested_query_tags_preserve_the_complete_user_message() {
        let message = "环境说明\n<user_query>内层问题</user_query>\n补充说明";
        let wrapped = format!("<user_query>\n{message}\n</user_query>");
        assert_eq!(visible_user_text(&wrapped), message);
    }

    #[test]
    fn reads_user_query_and_tool_call() {
        let text = r#"{"type":"message","role":"user","sessionId":"s1","cwd":"D:\\proj","timestamp":1786438530912,"content":[{"type":"input_text","text":"<user_query>\n修一下登录\n</user_query>"}]}
{"type":"function_call","name":"read_file","callId":"c1","sessionId":"s1","timestamp":1786438531000,"arguments":"{\"path\":\"main.py\"}"}
{"type":"function_call_result","callId":"c1","sessionId":"s1","timestamp":1786438532000,"status":"completed","output":{"content":"ok"}}
{"type":"message","role":"assistant","sessionId":"s1","timestamp":1786438533000,"content":[{"type":"output_text","text":"改好了"}]}
{"type":"ai-title","aiTitle":"修登录","sessionId":"s1","timestamp":1786438533000}
"#;
        let parsed = WorkBuddy::from_text(text).unwrap();
        let common = WorkBuddy::to_common(&parsed).unwrap();
        assert_eq!(common.meta.id, "s1");
        assert_eq!(common.meta.title.as_deref(), Some("修登录"));
        assert_eq!(common.body[0].content, vec![Block::Text { text: "修一下登录".into() }]);
        let again = WorkBuddy::from_common(&common).unwrap();
        let round = WorkBuddy::to_common(&again).unwrap();
        assert_eq!(round.body[0].content, common.body[0].content);
        let qwen = crate::harness::qwen_work::QwenWork::from_common(&common).unwrap();
        let via_qwen = crate::harness::qwen_work::QwenWork::to_common(&qwen).unwrap();
        assert_eq!(via_qwen.body[0].content, common.body[0].content);
        let doubao = crate::harness::doubao_work::DoubaoWork::from_common(&common).unwrap();
        let via_doubao = crate::harness::doubao_work::DoubaoWork::to_common(&doubao).unwrap();
        assert_eq!(via_doubao.body[0].content, common.body[0].content);
    }

    #[test]
    fn slug_matches_windows_project_dir() {
        assert_eq!(project_slug(r"C:\Users\name\proj"), "c-Users-name-proj");
    }

    #[test]
    fn save_and_load_roundtrip_in_temp_dir() {
        let root = std::env::temp_dir().join(format!("txcript-wb-{}", Uuid::new_v4()));
        let store = WorkBuddyStore::new(&root);
        let text = r#"{"type":"message","role":"user","sessionId":"s1","cwd":"D:\\proj","timestamp":1786438530912,"content":[{"type":"input_text","text":"<user_query>\n修一下登录\n</user_query>"}]}
{"type":"message","role":"assistant","sessionId":"s1","cwd":"D:\\proj","timestamp":1786438533000,"content":[{"type":"output_text","text":"改好了"}]}
"#;
        let native = WorkBuddy::from_text(text).unwrap();
        let common = WorkBuddy::to_common(&native).unwrap();
        let saved = store.save(&WorkBuddy::from_common(&common).unwrap()).unwrap();
        let loaded = store.load(&saved.reference).unwrap();
        let back = WorkBuddy::to_common(&loaded).unwrap();
        assert_eq!(back.body[0].content, common.body[0].content);
        assert_eq!(back.body[1].content, common.body[1].content);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn live_install_parses_without_dropping_user_text() {
        let Some(store) = WorkBuddyStore::default_root() else {
            return;
        };
        let found = store.discover().unwrap();
        if found.is_empty() {
            return;
        }
        let mut parsed = 0;
        for item in found.iter().take(5) {
            let native = store.load(&item.reference).unwrap();
            let common = WorkBuddy::to_common(&native).unwrap();
            assert!(!native.body.is_empty(), "empty session file");
            if common.body.iter().any(|m| m.role == Role::User) {
                parsed += 1;
            }
        }
        assert!(parsed > 0, "no user text survived conversion");
    }

    #[test]
    fn overseas_tree_roundtrips_with_its_own_name() {
        let root = std::env::temp_dir().join(format!("txcript-wbai-{}", Uuid::new_v4()));
        let store = WorkBuddyAiStore::new(&root);
        let text = r#"{"type":"message","role":"user","sessionId":"s1","cwd":"D:\\proj","timestamp":1786438530912,"content":[{"type":"input_text","text":"<user_query>\n修一下登录\n</user_query>"}]}
{"type":"message","role":"assistant","sessionId":"s1","cwd":"D:\\proj","timestamp":1786438533000,"content":[{"type":"output_text","text":"改好了"}]}
"#;
        let native = WorkBuddyAi::from_text(text).unwrap();
        let common = WorkBuddyAi::to_common(&native).unwrap();
        let saved = store.save(&WorkBuddyAi::from_common(&common).unwrap()).unwrap();
        let back = WorkBuddyAi::to_common(&store.load(&saved.reference).unwrap()).unwrap();
        assert_eq!(back.meta.id, "s1");
        assert_eq!(back.body[0].content, common.body[0].content);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn live_overseas_install_parses() {
        if std::env::var_os("WORKBUDDY_AI_DIR").is_some() {
            return;
        }
        let Some(store) = WorkBuddyAiStore::default_root() else {
            return;
        };
        assert!(store.root.ends_with(".workbuddy-ai"));
        let found = store.discover().unwrap();
        if found.is_empty() {
            return;
        }
        let native = store.load(&found[0].reference).unwrap();
        let common = WorkBuddyAi::to_common(&native).unwrap();
        assert!(!native.body.is_empty());
        assert_eq!(common.meta.id, found[0].meta.id);
    }
}
