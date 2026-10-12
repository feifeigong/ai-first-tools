#![allow(clippy::expect_used, clippy::panic, clippy::unwrap_used)]

use serde_json::{Value, json};
use txcript::common::{Block, ToolOutput};
use txcript::harness::{claude_chat::ClaudeChat, claude_code::ClaudeCode};
use txcript::{Codec, TextCodec};

/// Claude.ai adds UUIDs to tool-result content blocks. Passing them through
/// to Claude Code caused HTTP 400 on resume: `tool_result.content.0.text.uuid:
/// Extra inputs are not permitted`. Strip block UUIDs only when exporting;
/// keep native records, Common payloads, tool pairing, and the actual output.
#[test]
fn claude_chat_tool_result_block_uuids_do_not_reach_claude_code() {
    let cases = [
        (
            json!([{"type":"text","text":"tool output","uuid":"web-block"}]),
            json!([{"type":"text","text":"tool output"}]),
        ),
        (
            json!([{
                "type":"search_result", "uuid":"web-search", "title":"Result",
                "source":"https://example.com", "citations":{"enabled":true},
                "content":[{"type":"text","text":"excerpt","uuid":"web-excerpt"}]
            }]),
            json!([{
                "type":"search_result", "title":"Result",
                "source":"https://example.com", "citations":{"enabled":true},
                "content":[{"type":"text","text":"excerpt"}]
            }]),
        ),
        (
            json!([{
                "type":"document", "uuid":"web-document", "title":"Notes",
                "source":{"type":"content","content":[
                    {"type":"text","text":"notes","uuid":"web-notes"}
                ]}
            }]),
            json!([{
                "type":"document", "title":"Notes",
                "source":{"type":"content","content":[{"type":"text","text":"notes"}]}
            }]),
        ),
        // Supported fields and media must survive without being flattened.
        (
            json!([
                {"type":"text","text":"{\"uuid\":\"payload-id\"}","cache_control":{"type":"ephemeral"},"citations":[]},
                {"type":"image","source":{"type":"base64","media_type":"image/png","data":"cG5n"}},
                {"type":"tool_reference","tool_name":"Read"}
            ]),
            json!([
                {"type":"text","text":"{\"uuid\":\"payload-id\"}","cache_control":{"type":"ephemeral"},"citations":[]},
                {"type":"image","source":{"type":"base64","media_type":"image/png","data":"cG5n"}},
                {"type":"tool_reference","tool_name":"Read"}
            ]),
        ),
        // UUIDs in arbitrary tool data are output, not block metadata.
        (
            json!({"uuid":"payload-id","content":[{"uuid":"child-id"}]}),
            json!(json!({"uuid":"payload-id","content":[{"uuid":"child-id"}]}).to_string()),
        ),
        (
            json!([{"type":"unknown","uuid":"payload-id"}]),
            json!(json!([{"type":"unknown","uuid":"payload-id"}]).to_string()),
        ),
    ];

    for (input, expected) in cases {
        assert_conversion(input, &expected);
    }
}

fn assert_conversion(input: Value, expected: &Value) {
    let source = json!({
        "uuid":"11111111-1111-4111-8111-111111111111",
        "created_at":"2026-01-02T03:04:05.000Z",
        "chat_messages":[{
            "uuid":"22222222-2222-4222-8222-222222222222",
            "sender":"assistant",
            "created_at":"2026-01-02T03:04:05.000Z",
            "content":[
                {"type":"tool_use","id":"tool-1","name":"Lookup","input":{"query":"example"}},
                {"type":"tool_result","tool_use_id":"tool-1","is_error":true,"content":input}
            ]
        }]
    });
    let chat = ClaudeChat::from_text(&source.to_string()).unwrap();
    let common = ClaudeChat::to_common(&chat).unwrap();
    assert_eq!(
        common.body[1].content,
        vec![Block::ToolResult {
            tool_use_id: "tool-1".into(),
            content: ToolOutput::Json(input),
            is_error: true,
        }]
    );

    let code = ClaudeCode::from_common(&common).unwrap();
    let encoded = ClaudeCode::to_text(&code).unwrap();
    let lines: Vec<Value> = encoded
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert_eq!(lines[0]["message"]["content"][0]["id"], "tool-1");
    assert_eq!(
        lines[1]["message"]["content"][0],
        json!({
            "type":"tool_result","tool_use_id":"tool-1","content":expected,"is_error":true
        })
    );
    assert_eq!(ClaudeChat::to_common(&chat).unwrap(), common);
    assert_eq!(
        serde_json::from_str::<Value>(&ClaudeChat::to_text(&chat).unwrap()).unwrap(),
        source
    );

    // Native Claude Code load/save must still preserve source metadata.
    let mut original = lines;
    original[1]["message"]["content"][0]["content"] =
        source["chat_messages"][0]["content"][1]["content"].clone();
    let original_text = original
        .iter()
        .map(Value::to_string)
        .collect::<Vec<_>>()
        .join("\n");
    let reloaded = ClaudeCode::from_text(&original_text).unwrap();
    let saved: Vec<Value> = ClaudeCode::to_text(&reloaded)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    assert_eq!(saved, original);
}
