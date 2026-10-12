#![allow(clippy::expect_used, clippy::panic, clippy::unwrap_used, missing_docs)]

//! Deterministic search benchmarks: index build over 100 synthetic sessions
//! (20,000 messages) and per-keystroke-shaped queries against it.
//! Reproducible on any machine — for numbers against the real sessions on
//! *this* machine, use `cargo run --release --example search_bench`.

use std::hint::black_box;

use chrono::DateTime;
use criterion::{Criterion, criterion_group, criterion_main};
use txcript::common::{Block, Message, Meta, Role};
use txcript::search::{DocKey, Index, Query};
use txcript::{Common, HarnessId, Transcript};

const SESSIONS: usize = 100;
const MESSAGES: usize = 200;

/// Varied, non-repeating text so the matcher can't shortcut on identical
/// lines; seeded by session and message index, no RNG.
fn session(s: usize) -> Transcript<Common> {
    let ts = |secs: i64| DateTime::from_timestamp(1_780_000_000 + secs, 0).unwrap();
    let words = [
        "relay",
        "protocol",
        "websocket",
        "reconnect",
        "parser",
        "index",
        "cursor",
        "session",
        "timeout",
        "handshake",
        "buffer",
        "fragment",
    ];
    let base = i64::try_from(s).unwrap() * 10_000;
    let meta = Meta {
        id: format!("bench-{s}"),
        timestamp: ts(base),
        cwd: Some(format!("/work/repo-{}", s % 7)),
        git_branch: Some("main".to_string()),
        title: Some(format!(
            "session {s} on the {} rework",
            words[s % words.len()]
        )),
        cli_version: None,
        model: Some("claude-opus-4-8".to_string()),
        lineage: None,
    };
    let body = (0..MESSAGES)
        .map(|m| {
            let (role, model) = if m % 2 == 0 {
                (Role::User, None)
            } else {
                (Role::Assistant, Some("claude-opus-4-8".to_string()))
            };
            let a = words[(s + m) % words.len()];
            let b = words[(s * 3 + m * 5) % words.len()];
            Message {
                role,
                content: vec![Block::Text {
                    text: format!(
                        "turn {m}: the {a} {b} path drops frame {} under load",
                        m * 7
                    ),
                }],
                timestamp: ts(base + i64::try_from(m).unwrap()),
                model,
                stop_reason: None,
                usage: None,
            }
        })
        .collect();
    Transcript::new(meta, body)
}

fn build_index() -> Index {
    let mut index = Index::new();
    for s in 0..SESSIONS {
        index.insert(
            DocKey {
                harness: HarnessId::ClaudeCode,
                id: format!("bench-{s}"),
                source: None,
            },
            &session(s),
        );
    }
    index
}

fn search_benches(c: &mut Criterion) {
    let transcripts: Vec<_> = (0..SESSIONS).map(session).collect();
    c.bench_function("index_build_100_sessions", |b| {
        b.iter(|| {
            let mut index = Index::new();
            for (s, t) in transcripts.iter().enumerate() {
                index.insert(
                    DocKey {
                        harness: HarnessId::ClaudeCode,
                        id: format!("bench-{s}"),
                        source: None,
                    },
                    black_box(t),
                );
            }
            index
        });
    });

    let index = build_index();
    let mut keystroke = Query::fuzzy("relay protocol reconnect");
    keystroke.limit = Some(64);
    for (name, query) in [
        (
            "query_fuzzy_20k_msgs",
            Query::fuzzy("relay protocol reconnect"),
        ),
        ("query_substring_20k_msgs", Query::substring("drops frame")),
        ("query_keystroke_limit64_20k_msgs", keystroke),
    ] {
        c.bench_function(name, |b| {
            b.iter(|| index.query(black_box(&query)));
        });
    }
}

criterion_group!(benches, search_benches);
criterion_main!(benches);
