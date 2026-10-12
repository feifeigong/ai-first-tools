#![allow(clippy::expect_used, clippy::panic, clippy::unwrap_used, missing_docs)]

//! Deterministic codec benchmarks on a synthetic 200-message session:
//! JSONL parse, the two Common conversions, and a full cross-harness
//! convert. Reproducible on any machine — for profiling against the real
//! sessions on *this* machine, use `cargo run --release --example
//! search_bench` instead.

use std::hint::black_box;

use chrono::DateTime;
use criterion::{Criterion, criterion_group, criterion_main};
use txcript::common::{Block, Message, Meta, Role, Tool, ToolOutput};
use txcript::harness::{claude_code, codex};
use txcript::{Codec, Common, TextCodec, Transcript, convert};

/// 50 exchanges of user ask → assistant thinking+text → Edit call → result:
/// 200 messages, in the shape and size of a real working session.
fn synthetic_session() -> Transcript<Common> {
    let ts = |secs: i64| DateTime::from_timestamp(1_780_000_000 + secs, 0).unwrap();
    let meta = Meta {
        id: "bench-1".to_string(),
        timestamp: ts(0),
        cwd: Some("/work/repo".to_string()),
        git_branch: Some("main".to_string()),
        title: Some("bench session".to_string()),
        cli_version: Some("1.2.3".to_string()),
        model: Some("claude-opus-4-8".to_string()),
        lineage: None,
    };
    let mut body = Vec::new();
    for i in 0..50i64 {
        body.push(Message {
            role: Role::User,
            content: vec![Block::Text {
                text: format!("please fix failure {i} in the parser, it drops the {i}th field"),
            }],
            timestamp: ts(i * 4),
            model: None,
            stop_reason: None,
            usage: None,
        });
        body.push(Message {
            role: Role::Assistant,
            content: vec![
                Block::Thinking {
                    text: format!("field {i} is skipped when the index wraps at the boundary"),
                    signature: None,
                    encrypted: None,
                },
                Block::Text {
                    text: format!("Patching the bound for field {i}."),
                },
                Block::ToolUse {
                    id: format!("call-{i}"),
                    tool: Tool::Edit {
                        file_path: format!("/work/repo/src/parser_{i}.rs"),
                        old_string: format!("i <= {i}"),
                        new_string: format!("i < {i}"),
                        replace_all: false,
                    },
                },
            ],
            timestamp: ts(i * 4 + 1),
            model: Some("claude-opus-4-8".to_string()),
            stop_reason: None,
            usage: None,
        });
        body.push(Message {
            role: Role::User,
            content: vec![Block::ToolResult {
                tool_use_id: format!("call-{i}"),
                content: ToolOutput::Text(format!("applied edit {i}")),
                is_error: false,
            }],
            timestamp: ts(i * 4 + 2),
            model: None,
            stop_reason: None,
            usage: None,
        });
        body.push(Message {
            role: Role::Assistant,
            content: vec![Block::Text {
                text: format!("Done with failure {i}; the parser keeps the field now."),
            }],
            timestamp: ts(i * 4 + 3),
            model: Some("claude-opus-4-8".to_string()),
            stop_reason: None,
            usage: None,
        });
    }
    Transcript::new(meta, body)
}

fn codec_benches(c: &mut Criterion) {
    let common = synthetic_session();
    let native = claude_code::ClaudeCode::from_common(&common).unwrap();
    let jsonl = claude_code::ClaudeCode::to_text(&native).unwrap();

    c.bench_function("claude_parse_200_msgs", |b| {
        b.iter(|| claude_code::ClaudeCode::from_text(black_box(&jsonl)).unwrap());
    });
    c.bench_function("claude_to_common_200_msgs", |b| {
        b.iter(|| claude_code::ClaudeCode::to_common(black_box(&native)).unwrap());
    });
    c.bench_function("claude_from_common_200_msgs", |b| {
        b.iter(|| claude_code::ClaudeCode::from_common(black_box(&common)).unwrap());
    });
    c.bench_function("convert_claude_to_codex_200_msgs", |b| {
        b.iter(|| convert::<claude_code::ClaudeCode, codex::Codex>(black_box(&native)).unwrap());
    });
}

criterion_group!(benches, codec_benches);
criterion_main!(benches);
