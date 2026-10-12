# OpenCode

OpenCode is an open-source terminal coding agent built by the SST team
([github.com/sst/opencode](https://github.com/sst/opencode)). There is no
published transcript spec; the open-source storage and export code serves as
the spec. This document is grounded in that source (permalinks below), in
txcript's parser (`src/harness/opencode.rs`), and in inspection of real local
sessions.

```
~/.local/share/opencode/opencode.db          (one SQLite DB for everything)
│
├─ session   1 row  ─ id "ses_…", directory, title, version,
│                     time_created, time_archived, model (JSON)
├─ message   n rows ─ session_id, time_created, data (JSON: role, modelID,
│                     finish, tokens, …)
└─ part      m rows ─ message_id, session_id, data (JSON: one typed part)

session ──< message ──< part      reassembled as the `opencode export` shape:
                                  { info, messages: [ { info, parts: […] } ] }
```

## On disk

Everything lives in one SQLite database, managed by Drizzle ORM inside
OpenCode: `$XDG_DATA_HOME/opencode/opencode.db`, defaulting to
`~/.local/share/opencode/opencode.db`. txcript resolves the path as
`OPENCODE_DB` env var, then `$XDG_DATA_HOME/opencode/opencode.db`, then the
`~/.local/share` fallback (`OpenCodeStore::default_db`). A sibling `storage/`
directory of per-record JSON files is the pre-SQLite layout; OpenCode migrates
it into the DB on upgrade and txcript reads only the DB.

The DB holds more than transcripts (`project`, `todo`, cost/token rollups on
`session`); txcript reads three tables. `message.data` and `part.data` are
JSON text columns — the schema is relational only down to the message/part
grain, opaque JSON below that.

Discovery is one query: `session` rows where `time_archived IS NULL`, newest
first. Since all sessions share the one file, a store `Ref` is just the
session id. Loading a session selects its `message` rows (ordered by
`time_created`, then id) and `part` rows (grouped by message, ordered by id),
and assembles the same `{info, messages: [{info, parts}]}` document that
`opencode export` emits — that export shape, not the raw rows, is txcript's
native `Body` for this harness.

## Dissection of a transcript

| Their name | What it is | Maps to |
|---|---|---|
| session | Header row: id (`ses_…`), directory, title, version, created time, model, `parent_id` | `Meta` — id, timestamp, cwd, title, cli_version, model, lineage (`git_branch` is never available) |
| message | One turn: `data` JSON with `role`, plus `modelID`, `finish`, `tokens` on assistant turns | One or more Common `Message`s, `Role::User` / `Role::Assistant` |
| part `text` | Prose; `"synthetic": true` marks harness-injected text | `Block::Text` (synthetic dropped) |
| part `reasoning` | Model thinking | `Block::Thinking` (no signature) |
| part `file` | Attachment as a `data:` URL with a `mime` | `Block::Image` when the mime is `image/*` |
| part `tool` | Whole call lifecycle in one record: `tool`, `callID`, `state {status, input, output/error}` | `Block::ToolUse` + `Block::ToolResult`, paired by `callID` |
| part `step-start` / `step-finish` / `snapshot` / `patch` … | Agent-loop bookkeeping | Dropped from the conversation (kept in the native body) |

Two structural translations do most of the work. First, OpenCode keeps a tool
call and its result in a single `tool` part; txcript splits it Anthropic-style
into a `ToolUse` on an assistant message and a `ToolResult` on a following
user message (an error status becomes `is_error: true`; a still
pending/running call emits the use with no result). Second, one OpenCode
assistant message becomes several Common messages, cut at each tool part;
the turn-level `tokens` and `finish` attach to the turn's last assistant
message as `Usage` and `StopReason` (`stop` → `EndTurn`, `length` →
`MaxTokens`, etc.). Lowercase tool names normalize to canonical ones —
`edit` → `Edit` with `filePath`/`oldString`/`newString` renamed to snake_case
— and unknown tools pass through as `Tool::Raw`. Placeholder titles
(`New session - …`) are treated as absent.

A synthetic message record, shaped like the real thing:

```json
{
  "info": {
    "id": "msg_0123abcd", "sessionID": "ses_0123abcd", "role": "assistant",
    "modelID": "claude-opus-4-7", "providerID": "anthropic",
    "finish": "stop", "cost": 0,
    "tokens": { "input": 6, "output": 88, "cache": { "read": 10, "write": 21428 } },
    "time": { "created": 1778834704540, "completed": 1778834704999 }
  },
  "parts": [
    { "type": "step-start" },
    { "type": "reasoning", "text": "The rename is mechanical." },
    { "type": "tool", "tool": "edit", "callID": "call_1",
      "state": { "status": "completed",
                 "input": { "filePath": "/repo/a.rs", "oldString": "old", "newString": "new" },
                 "output": "done" } },
    { "type": "text", "text": "Renamed it." }
  ]
}
```

## Lineage

`session.parent_id` names the session that spawned this one — OpenCode's subagent/task tool
starts a child session with its own row. A non-empty value always becomes a Spawn
`Meta.lineage`; it's a bare column read, so `discover` (one extra `SELECT` column) and `load`
both fill it with no added query. OpenCode has no fork or continue relation that reuses this
column. `from_common`/`opencode import` never writes it.

## Caveats

- **Writes go through the CLI, not the DB.** txcript opens the database
  read-only; `save` serializes the export shape to a private temp file and
  shells out to `opencode import` (the binary must be on PATH), letting
  OpenCode own its schema. `import` rejects session ids that don't start with
  `ses`, so foreign UUIDs are deterministically re-shaped.
- **Delete is archive.** `delete` sets `time_archived`; rows remain and the
  session is recoverable from OpenCode's UI. Discovery filters archived rows.
- **Schema drift.** The schema is Drizzle-migrated and moves quickly (the
  `session` table keeps growing columns). txcript touches only the stable
  core: `session(id, directory, title, version, time_created, time_archived,
  model, parent_id)`, `message(id, session_id, time_created, data)`,
  `part(id, message_id, session_id, data)`. Channel builds may write
  `opencode-<channel>.db`; only `opencode.db` is discovered.
- **Lossiness in Common.** Bookkeeping and synthetic parts are dropped;
  per-part timestamps collapse to the message's; a tool result shares its
  call's timestamp after a round-trip; `EndTurn`, `StopSequence`, `Aborted`,
  and `Other` stop reasons all re-export as `"stop"` (OpenCode requires a
  finish and has no spelling for the rest). Same-harness round-trips through
  Common are fixpoint-tested, not byte-identical.
- **Hostile input.** A `part` row whose JSON doesn't parse is dropped and the
  message survives; unknown or missing roles are skipped; an absent DB means
  "no sessions", not an error. The import staging file is created
  `create_new` + mode 0600 under a randomized name.

## References

- Drizzle tables `session` / `message` / `part`:
  <https://github.com/sst/opencode/blob/3a90639cb57619a21e59f544b3e8d23ffed56f48/packages/core/src/session/sql.ts>
- Export shape `{info, messages: [{info, parts}]}`:
  <https://github.com/sst/opencode/blob/3a90639cb57619a21e59f544b3e8d23ffed56f48/packages/opencode/src/cli/cmd/export.ts>
- DB filename and channel-suffix logic:
  <https://github.com/sst/opencode/blob/3a90639cb57619a21e59f544b3e8d23ffed56f48/packages/core/src/database/database.ts>
- XDG data-dir resolution:
  <https://github.com/sst/opencode/blob/3a90639cb57619a21e59f544b3e8d23ffed56f48/packages/core/src/global.ts>
- Legacy JSON `storage/` tree and its migration:
  <https://github.com/sst/opencode/blob/3a90639cb57619a21e59f544b3e8d23ffed56f48/packages/opencode/src/storage/storage.ts>

Last verified: 2026-09-26, against src/harness/opencode.rs and real local
sessions. The authoritative mapping is `src/harness/opencode.rs` (codec,
tool-name normalization, SQLite store) with `tests/integration/opencode.rs`
as executable shape examples.
