# Antigravity

Antigravity is Google's agent harness; txcript reads the conversation store of
its terminal surface, the **Antigravity CLI** (`agy`) — not the Antigravity
IDE. The CLI is closed source: the GitHub repository is a changelog and issue
tracker with no implementation, and Google's docs describe conversation
*management*, never the storage format. Everything below is
**reverse-engineered** — the SQLite schema from observed session databases,
and the protobuf field numbers from the message descriptors embedded in the
`agy` binary itself. Observations are from `agy` 1.0.16.

Each conversation is one small SQLite database of protobuf-encoded
"trajectory steps", plus a `brain/<id>/` working directory whose generated
logs mirror the conversation as JSONL for display:

```
~/.gemini/antigravity-cli/
├── conversations/
│   └── <uuid>.db                 # SQLite: the resume carrier
│       ├── trajectory_meta       # 1 row: trajectory_id, cascade_id (= session id)
│       ├── steps                 # the conversation, one protobuf Step per row
│       │     idx | step_type | status | metadata | step_payload | ...
│       │                                └─ gemini_coder.Step:
│       │                                     1: step-type tag
│       │                                     4: status
│       │                                     5: CortexStepMetadata (ts, tool call, usage)
│       │                                     N: one payload message per step kind
│       ├── trajectory_metadata_blob   # "main" row: workspace, branch, created-at
│       └── gen_metadata, executor_metadata, parent_references, battle_mode_infos
└── brain/<uuid>/.system_generated/logs/
    ├── transcript.jsonl          # display mirror of the steps
    └── transcript_full.jsonl
```

## On disk

The data root is `~/.gemini/antigravity-cli` (resolved via `HOME`, or
`USERPROFILE` on Windows; there is no dedicated environment override — an
alternate root is passed programmatically via `AntigravityStore::new`).
Conversations live at `conversations/<uuid>.db`, plain SQLite with
`PRAGMA user_version = 1` and the usual `-wal`/`-shm` sidecars while the CLI
is live. Discovery lists `*.db` files in that directory and opens each
read-only; files that don't parse as an Antigravity database (older `.pb`
files, foreign SQLite) are silently skipped. The database is the resume
carrier — `agy --conversation=<id>` rebuilds context from the steps alone —
but a missing `brain/<id>/` directory wedges the CLI on resume, so txcript's
`save` always writes both.

## Dissection of a transcript

Names below are Antigravity's own, as recovered from the descriptors in the
`agy` binary (`gemini_coder.Step`, `exa.cortex_pb.*`,
`exa.codeium_common_pb.*`).

| Their name | What it is | Maps to |
| --- | --- | --- |
| `trajectory_meta.cascade_id` | The conversation/session id (a UUID, also the db filename stem) | `Meta.id` |
| `trajectory_metadata_blob` "main" row (`CortexTrajectoryMetadata`) | Workspace URI, git branch, created-at timestamp | `Meta.cwd`, `Meta.git_branch`, `Meta.timestamp` |
| `steps` row | One trajectory step: `idx`, `step_type`, `status`, blob columns | One `Message` (or bookkeeping, dropped) |
| `step_payload` (`gemini_coder.Step`) | The step's protobuf: type tag, status, metadata envelope, per-kind payload | decoded per step kind |
| `CortexStepMetadata` (field 5) | Timestamp, source, the tool call, model id, token usage | `Message.timestamp`, `model`, `Usage` |
| `CortexStepUserInput` (type 14) | The user's prompt text and inline images | `Role::User` message with `Text`/`Image` blocks |
| `CortexStepPlannerResponse` (type 15) | Model turn: thinking + signature, response text, `ChatToolCall`s, stop reason | `Role::Assistant` message with `Thinking`/`Text`/`ToolUse` blocks |
| `ChatToolCall` `{id, name, arguments_json}` | A tool invocation, embedded in the planner step *and* mirrored into the executing step's metadata | `Block::ToolUse { id, tool }` |
| Tool steps (types 21, 8, 9, 5, 7, 38, 132) | `RUN_COMMAND`, `VIEW_FILE`, `LIST_DIRECTORY`, `CODE_ACTION`, `GREP_SEARCH`, `MCP_TOOL`, generic | `Role::User` message with one `Block::ToolResult` |
| `status` (1/3/6/7) | Pending / done / canceled / error | pending → no result yet; error/canceled → `is_error` |
| Checkpoint (23), history (98), system (101), ephemeral (90) steps | Summaries, context markers, injected notices | dropped from messages; checkpoint title feeds `Meta.title` |
| `brain/.../transcript*.jsonl` | Display-log mirror of the steps | carried verbatim, regenerated on write |

Threading is flat: steps are ordered by `idx`, and tool calls pair with their
results by call id — the planner step declares the `ChatToolCall`, and the
step that executed it carries the same call in its `CortexStepMetadata`. Any
completed step whose metadata holds a tool call becomes that call's result
message. Native tool names normalize onto txcript's canonical tools
(`run_command` → Bash, `view_file` → Read, `write_to_file` → Write,
`replace_file_content` → Edit); anything else — `list_dir`, `grep_search`,
MCP tools — passes through as `Tool::Raw`. Metadata extraction prefers the
"main" trajectory blob, falling back to the earliest step timestamp and, for
the title, the latest checkpoint's summary else the first user message
truncated to 80 chars.

txcript's *text* form of a session is JSON with every blob hex-encoded — the
step below is a real encoding of a user turn (`step_type` 14, done, with a
timestamp/source metadata envelope and the `CortexStepUserInput` payload in
field 19):

```json
{
  "idx": 0,
  "step_type": 14,
  "status": 3,
  "metadata": "0a0608a0dbe1c4061804",
  "step_payload": "080e20032a0a0a0608a0dbe1c40618049a012a12124669782074686520666c616b7920746573741a140a124669782074686520666c616b792074657374"
}
```

## Caveats

- **Reverse-engineered; expect drift.** Field numbers come from descriptors
  in the `agy` 1.0.16 binary and sessions observed 2026-08. New step types
  decode as empty results rather than dropped records; unknown enum values
  survive as `stop-<n>` / `model-<n>` strings.
- **Blob-level losslessness only.** Every table row round-trips
  byte-for-byte through the native body, but conversion through Common
  drops: `toolAction`/`toolSummary` display strings inside typed tool args,
  per-call binary `thinking_signature` blobs, and bookkeeping steps'
  message-level presence. Edit/Write results are derived data and come back
  as canonical `{"file": …, "edited"|"created": true}` JSON; assistant-side
  images flatten to placeholder text.
- **Models are numeric.** Antigravity stores a model enum; txcript surfaces
  `model-<n>` and cannot map foreign model names back on write.
- **Tolerant protobuf reader.** A corrupt blob yields its readable prefix,
  never an error — hostile or truncated databases degrade to shorter views.
  Deletion is containment-checked: the db must resolve inside
  `conversations/` and the id must be a plain path component before the db,
  its WAL sidecars, and `brain/<id>/` are removed.
- **Feature-gated store.** Reading/writing the SQLite store requires
  txcript's `opencode` cargo feature (the shared rusqlite dependency);
  without it the codec still converts the JSON text form.
- The CLI stamps a fixed `WaitMsBeforeAsync: 2000` on every command; any
  other value keeps the call `Tool::Raw` rather than lying on round-trip.

## References

No public specification of this format exists. Google's CLI docs
([antigravity.google/docs/cli/conversations](https://antigravity.google/docs/cli/conversations),
accessed 2026-08-10) confirm SQLite conversation storage but document no
schema, and the public GitHub repository
([github.com/google-antigravity/antigravity-cli](https://github.com/google-antigravity/antigravity-cli),
accessed 2026-08-10) contains no source. This document is reverse-engineered
from observed `agy` 1.0.16 sessions and the binary's embedded descriptors.

The authoritative mapping is `src/harness/antigravity.rs`, exercised by
`tests/integration/antigravity.rs`.

Last verified: 2026-08-10, against src/harness/antigravity.rs and real local sessions.
