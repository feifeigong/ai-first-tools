# Claude Chat

Claude Chat conversations live on `claude.ai`, not in a txcript-managed local
directory. The web API is private and undocumented, so this integration is
reverse-engineered from Claude's shipped web client, a real signed-in
conversation, and independent community readers. It is deliberately
**pull-only**: txcript discovers and loads conversations with GET requests and
never creates, updates, deletes, or resumes one in Claude.

This is separate from Claude's official account data export. V1 does not read
the export ZIP, `conversations.json`, or an array of exported conversations.

## Access

On macOS, explicitly selecting Claude Chat reuses the signed-in Claude Desktop
session automatically:

```sh
txcript list --from claude_chat
```

`TXCRIPT_CLAUDE_CHAT_ORGANIZATION_UUID` optionally restricts discovery to one
organization. It also bypasses account-wide organization discovery if Claude
rejects that private endpoint for the Desktop session.

The explicit `--from claude_chat` selection permits txcript to copy Claude
Desktop's Chromium cookie database to a temporary directory, ask macOS
Keychain for `Claude Safe Storage`, and decrypt its current Claude cookies.
Expired Cloudflare state is discarded, and Desktop's `lastActiveOrg` selects
the same organization currently active in the app. Aggregate discovery, such
as `txcript list` without `--from`, does not contact Claude Chat. The MCP
tools' `from` field is the same gate: omitted, they scan local harnesses only,
and `list_sessions` refuses `claude_chat` outright.
The temporary copy is removed after credentials are read. Secrets are used only
in request headers and are never included in errors or debug output.

Environment-supplied credential material is explicitly disabled in V1.
`TXCRIPT_CLAUDE_CHAT_SESSION_KEY`, `TXCRIPT_CLAUDE_CHAT_CF_BM`, and
`TXCRIPT_CLAUDE_CHAT_CF_CLEARANCE` are rejected with guidance instead of being
used or silently ignored. Non-macOS platforms therefore cannot access Claude
Chat in V1.

## Remote store

The current read path is:

1. Select an explicitly configured organization, otherwise Claude Desktop's
   active organization; if neither is available, fall back to
   `GET /api/organizations`.
2. Paginate `GET /api/organizations/{org}/chat_conversations_v2` with
   `limit`, `offset`, and `consistency=strong`.
3. Load one conversation with
   `GET /api/organizations/{org}/chat_conversations/{conversation}` and
   `tree=True`, `rendering_mode=messages`, `render_all_tools=true`.
4. Fetch same-origin image previews referenced by the selected conversation.
5. When the active branch presents generated files, list its current sandbox
   with `GET /api/organizations/{org}/conversations/{conversation}/wiggle/list-files`
   and pull the selected paths with the matching `wiggle/download-file` GET.

The production origin is fixed to `https://claude.ai`; there is no base-URL
override that could redirect credentials. Requests use a matching Chromium
TLS, HTTP/2, and header profile because Claude's edge rejects generic HTTP
clients even when their session cookie is valid. Redirects are disabled so a
Claude Desktop cookie cannot follow a response to another origin.
Same-origin image and generated-file bytes are stored inside the native body
under txcript's `$txcript_images` and `$txcript_files` keys. Images become
base64 Common image blocks; generated files ride through Common on the
corresponding `local_resource` tool result. External attachment URLs are not
fetched.

Discovery returns each conversation's UUID, title, creation time, model, and
an update-time fingerprint. Direct Rust calls to
`ClaudeChatStore::discover()` produce a compile-time warning that discovery
enumerates the selected account's conversation list through an undocumented
private endpoint Anthropic can observe or restrict. Authentication failures
and recognizable protocol drift are reported when `--from claude_chat` is
explicit. All-harness scans skip Claude Chat entirely so they cannot enumerate
remote conversations by surprise.

## Conversation shape

One detail response is an object containing:

```text
uuid, name, created_at, updated_at, model
current_leaf_message_uuid
chat_messages[]
  uuid, parent_message_uuid, sender, created_at
  text, content[], files[], files_v2[], attachments[]
```

The native body keeps `chat_messages` as raw JSON and all other server keys in
a flattened map. Unknown server fields and content blocks therefore survive
the text boundary even when Common cannot represent them.

Messages form a parent-linked tree. The codec follows
`current_leaf_message_uuid` to the root and converts that active branch. A
missing, cyclic, or broken graph falls back to server order instead of dropping
turns. Structured `content` takes precedence over the duplicate message-level
`text` field.

| Claude block | Common mapping |
|---|---|
| `text` | `Block::Text` |
| `thinking` / `reasoning` | `Block::Thinking` |
| `tool_use` | normalized typed tool or lossless `Tool::Raw` |
| `tool_result` | user-carried `Block::ToolResult` |
| inline or hydrated image | `Block::Image` |
| `artifact` / `document`, or a hydrated presented file | `Block::Artifact` |

Live tool names are normalized to their Claude Code equivalents where the
arguments fit: `bash_tool` becomes `Bash`, `view` becomes `Read`, and
`create_file` becomes `Write` and also contributes a text artifact when its
input includes the full `file_text`. Older `artifacts` create/rewrite tools
similarly contribute their complete content; update patches remain tool
records, since a patch alone is not a complete file. `present_files` remains a raw tool event, while
each file it presents becomes a first-class Common artifact carrying its
identity, filename, MIME type, and bytes. When writing Claude Code, the generic
Common artifact path materializes those bytes under the generated session's
`artifacts/` sidecar and emits Claude Code's native `Artifact` tool with the
absolute file path. The base64 payload is not copied into JSONL.

Claude's sandbox endpoint addresses the current file by path, not historical
artifact UUID. If a conversation presented the same path repeatedly, txcript
hydrates only the final active-branch presentation rather than assigning the
current bytes to older revisions.

Claude may colocate a tool call, its result, and later assistant text inside
one assistant message. The codec fans that record into assistant → user →
assistant Common messages while preserving block order. Explicit tool IDs win;
otherwise deterministic UUIDv5 IDs pair a result with the nearest preceding
call.

## Refusals and losses

- `Codec::from_common`, `Store::save`, and `Store::delete` always return a
  source-only error.
- `txcript continue <claude-id>` without another target is refused, as is any
  `--with claude_chat`. Pulling into another writable harness is supported.
- Side branches, citations, feedback/UI state, unknown blocks, external
  attachments, and generated files no longer available in Claude's sandbox
  remain in the native response but have no Common slot.
- The private endpoint, browser fingerprint, and Desktop cookie encryption can drift. Unsupported
  response or encryption shapes fail with guidance rather than guessing.

## References

- Claude's shipped web client, Claude Desktop's Chromium network profile, and
  a real conversation, inspected 2026-08-21.
- [rpeck/claude-explorer](https://github.com/rpeck/claude-explorer), an
  independent reader using the same organization/list/detail flow and Chrome
  transport impersonation.
- [daymade read-claude-web-conversation](https://github.com/daymade/claude-code-skills/blob/main/daymade-claude-code/read-claude-web-conversation/SKILL.md), which independently records the full-tree and
  `render_all_tools=true` detail request.
- [glebmish/claude-exporter sandbox-file notes](https://github.com/glebmish/claude-exporter/blob/main/docs/sandbox-files.md), independently grounded against the live `wiggle/list-files` and `wiggle/download-file` GET endpoints.
- Authoritative txcript mapping: `src/harness/claude_chat.rs` and
  `tests/integration/claude_chat.rs`.
