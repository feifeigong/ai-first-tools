#![allow(clippy::expect_used, clippy::panic, clippy::unwrap_used)]

//! Claude Chat's live response codec. The store's HTTP behavior is exercised
//! by in-module mock-server tests because its production origin is fixed.

use serde_json::{Value, json};
use txcript::common;
use txcript::harness::{claude_chat, claude_code};
use txcript::{Codec, Common, HarnessId, TextCodec, Transcript, convert};

fn native_fixture() -> Value {
    json!({
        "uuid": "11111111-1111-4111-8111-111111111111",
        "name": "Build a design note",
        "summary": "A rich Claude web conversation",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:03:00Z",
        "current_leaf_message_uuid": "44444444-4444-4444-8444-444444444444",
        "has_branches": true,
        "model": "claude-sonnet-4-6",
        "server_field_txcript_does_not_model": {"keep": true},
        "$txcript_images": {
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": {
                "type": "base64",
                "media_type": "image/png",
                "data": "cG5n"
            }
        },
        "chat_messages": [
            {
                "uuid": "22222222-2222-4222-8222-222222222222",
                "parent_message_uuid": null,
                "sender": "human",
                "created_at": "2026-08-20T10:00:00Z",
                "text": "Explain this image",
                "content": [{"type":"text","text":"Explain this image"}],
                "files": [{
                    "uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "file_type": "image/png",
                    "preview_url": "/api/files/preview"
                }],
                "message_field_txcript_does_not_model": [1, 2, 3]
            },
            {
                "uuid": "33333333-3333-4333-8333-333333333333",
                "parent_message_uuid": "22222222-2222-4222-8222-222222222222",
                "sender": "assistant",
                "created_at": "2026-08-20T10:01:00Z",
                "content": [{"type":"text","text":"This is the inactive branch."}]
            },
            {
                "uuid": "44444444-4444-4444-8444-444444444444",
                "parent_message_uuid": "22222222-2222-4222-8222-222222222222",
                "sender": "assistant",
                "created_at": "2026-08-20T10:02:00Z",
                "text": "Artifact ready.",
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 30,
                    "cache_read_input_tokens": 5
                },
                "content": [
                    {"type":"thinking","thinking":"I should inspect the image.","signature":"sig"},
                    {"type":"tool_use","name":"shell_command","input":{"cmd":"file image.png","cwd":"/tmp"}},
                    {"type":"tool_result","content":{"stdout":"PNG image data","exit_code":0}},
                    {"type":"text","text":"Artifact ready."},
                    {"type":"artifact","id":"artifact-1","title":"Design note","content":"# Note"},
                    {"type":"future_block","opaque":{"still":"native"}}
                ]
            }
        ]
    })
}

fn native() -> Transcript<claude_chat::ClaudeChat> {
    claude_chat::ClaudeChat::from_text(&serde_json::to_string(&native_fixture()).unwrap()).unwrap()
}

#[test]
fn text_round_trip_preserves_the_complete_live_response() {
    let first = native();
    let rendered = claude_chat::ClaudeChat::to_text(&first).unwrap();
    let second = claude_chat::ClaudeChat::from_text(&rendered).unwrap();
    assert_eq!(first, second);
    assert_eq!(
        second
            .body
            .extra
            .get("server_field_txcript_does_not_model")
            .unwrap()["keep"],
        true
    );
    assert_eq!(
        second.body.chat_messages[0]["message_field_txcript_does_not_model"],
        json!([1, 2, 3])
    );
}

#[test]
fn active_branch_maps_rich_blocks_and_splits_colocated_results() {
    let common = claude_chat::ClaudeChat::to_common(&native()).unwrap();
    assert_eq!(common.body.len(), 4);

    assert_eq!(common.body[0].role, common::Role::User);
    assert_eq!(
        common.body[0].content.len(),
        2,
        "top-level text is deduplicated"
    );
    assert!(matches!(
        &common.body[0].content[1],
        common::Block::Image { source }
            if source.media_type == "image/png" && source.data == "cG5n"
    ));
    assert!(common.body.iter().all(|message| {
        message.content.iter().all(|block| {
            !matches!(block, common::Block::Text { text } if text.contains("inactive branch"))
        })
    }));

    assert_eq!(common.body[1].role, common::Role::Assistant);
    assert!(matches!(
        &common.body[1].content[0],
        common::Block::Thinking { text, signature, .. }
            if text == "I should inspect the image." && signature.as_deref() == Some("sig")
    ));
    let tool_id = match &common.body[1].content[1] {
        common::Block::ToolUse {
            id,
            tool: common::Tool::Bash {
                command, workdir, ..
            },
        } if command == "file image.png" && workdir.as_deref() == Some("/tmp") => id.clone(),
        other => panic!("expected normalized Bash tool, got {other:?}"),
    };

    assert_eq!(common.body[2].role, common::Role::User);
    assert!(matches!(
        &common.body[2].content[0],
        common::Block::ToolResult {
            tool_use_id,
            content: common::ToolOutput::Json(value),
            is_error: false,
        } if tool_use_id == &tool_id && value["exit_code"] == 0
    ));

    assert_eq!(common.body[3].role, common::Role::Assistant);
    assert_eq!(
        common.body[3]
            .content
            .iter()
            .filter(|block| matches!(block, common::Block::Text { .. }))
            .count(),
        1,
        "message-level text is not duplicated"
    );
    assert!(matches!(
        &common.body[3].content[1],
        common::Block::Artifact { artifact }
            if artifact.id == "artifact-1"
                && artifact.name == "Design note"
                && matches!(&artifact.source, common::ArtifactSource::Text { text, .. }
                    if text == "# Note")
    ));
    assert_eq!(common.body[3].model.as_deref(), Some("claude-sonnet-4-6"));
    assert_eq!(
        common.body[3].stop_reason,
        Some(common::StopReason::EndTurn)
    );
    assert_eq!(common.body[3].usage.unwrap().input_tokens, 20);
}

#[test]
fn synthetic_tool_ids_are_deterministic() {
    let first = claude_chat::ClaudeChat::to_common(&native()).unwrap();
    let second = claude_chat::ClaudeChat::to_common(&native()).unwrap();
    assert_eq!(first, second);
}

#[test]
fn claude_chat_is_a_source_only_conversion_hop() {
    let native = native();
    let expected = claude_chat::ClaudeChat::to_common(&native).unwrap();
    let claude_code = convert::<claude_chat::ClaudeChat, claude_code::ClaudeCode>(&native).unwrap();
    let round = claude_code::ClaudeCode::to_common(&claude_code).unwrap();
    let signature = |transcript: &Transcript<Common>| {
        transcript
            .body
            .iter()
            .flat_map(|message| {
                message.content.iter().map(move |block| {
                    let value = match block {
                        common::Block::ToolResult { content, .. } => match content {
                            common::ToolOutput::Text(text) => text.clone(),
                            common::ToolOutput::Json(value) => value.to_string(),
                        },
                        common::Block::Artifact { artifact } => match &artifact.source {
                            common::ArtifactSource::Text { text, .. } => {
                                format!("artifact:text:{text}")
                            }
                            common::ArtifactSource::Base64 { data, .. } => {
                                format!("artifact:base64:{data}")
                            }
                            common::ArtifactSource::Path { path, .. } => {
                                format!("artifact:path:{path}")
                            }
                        },
                        other => serde_json::to_string(other).unwrap(),
                    };
                    (message.role, value)
                })
            })
            .collect::<Vec<_>>()
    };
    assert_eq!(signature(&round), signature(&expected));

    let error = claude_chat::ClaudeChat::from_common(&expected).unwrap_err();
    assert!(error.to_string().contains("live read-only source"));
}

#[test]
fn common_artifacts_materialize_into_claude_codes_native_artifact_tool() {
    let mut common = claude_chat::ClaudeChat::to_common(&native()).unwrap();
    common.body.push(common::Message {
        role: common::Role::Assistant,
        content: vec![common::Block::Artifact {
            artifact: common::Artifact {
                id: "artifact-file".to_string(),
                name: "Resume.docx".to_string(),
                source: common::ArtifactSource::Base64 {
                    data: "ZG9jeC1ieXRlcw==".to_string(),
                    media_type: Some(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            .to_string(),
                    ),
                },
            },
        }],
        timestamp: common.meta.timestamp,
        model: common.meta.model.clone(),
        stop_reason: Some(common::StopReason::EndTurn),
        usage: None,
    });
    let root = tempfile::tempdir().unwrap();
    let written = txcript::local::write(HarnessId::ClaudeCode, &common, Some(root.path())).unwrap();
    let text = std::fs::read_to_string(&written.location).unwrap();

    assert!(!text.contains("ZG9jeC1ieXRlcw=="));
    let native = claude_code::ClaudeCode::from_text(&text).unwrap();
    let round = claude_code::ClaudeCode::to_common(&native).unwrap();
    let artifact = round
        .body
        .iter()
        .flat_map(|message| &message.content)
        .find_map(|block| match block {
            common::Block::Artifact { artifact } if artifact.id == "artifact-file" => {
                Some(artifact)
            }
            _ => None,
        })
        .unwrap();
    let common::ArtifactSource::Path { path, .. } = &artifact.source else {
        panic!("Claude Code artifact is path-backed")
    };
    assert_eq!(std::fs::read(path).unwrap(), b"docx-bytes");
    assert!(text.contains("\"name\":\"Artifact\""));
    assert!(round.body.iter().any(|message| {
        message.content.iter().any(|block| {
            matches!(block, common::Block::ToolResult { tool_use_id, .. }
                if tool_use_id == "artifact-file")
        })
    }));
}

/// Like Amp, Claude Chat is server-authoritative and has no import path:
/// continuing into it is refused even when an output root is supplied.
#[test]
fn continuing_into_claude_chat_is_refused() {
    let common = claude_chat::ClaudeChat::to_common(&native()).unwrap();
    let dir = tempfile::tempdir().unwrap();
    for root in [None, Some(dir.path())] {
        let error = match txcript::local::write(HarnessId::ClaudeChat, &common, root) {
            Err(error) => error.to_string(),
            Ok(written) => panic!("expected refusal, wrote {}", written.location),
        };
        assert!(
            error.contains("never continued into Claude"),
            "unexpected error: {error}"
        );
    }
}

#[test]
fn aliases_do_not_steal_claude_from_claude_code() {
    assert_eq!(
        "claude".parse::<HarnessId>().unwrap(),
        HarnessId::ClaudeCode
    );
    assert_eq!(
        "claude-chat".parse::<HarnessId>().unwrap(),
        HarnessId::ClaudeChat
    );
    assert_eq!(
        "claude-web".parse::<HarnessId>().unwrap(),
        HarnessId::ClaudeChat
    );
}
