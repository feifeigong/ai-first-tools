# Amp

Amp is Sourcegraph's agentic coding tool (ampcode.com), available as a CLI and
editor extensions. It is closed source, and its public manual describes
*threads* — Amp's word for a session — only at the product level: nothing about
on-disk storage or the thread JSON schema is documented publicly. This document
is therefore **reverse-engineered**: from real thread files written by the
local-first-era CLI on this machine, and from txcript's parser
(`src/harness/amp.rs`), which is the authoritative mapping.

```
~/.local/share/amp/threads/
└── T-<uuid>.json ................ one pretty-printed JSON document per thread
    ├── v, id, created, title, agentMode, nextMessageId, ~debug
    ├── env.initial ............... { trees[], platform, tags[] }  (cwd, branch, CLI version, model)
    └── messages[] ................ alternating turns, Anthropic-style
        ├── role:"user" ........... content blocks: text | image | tool_result
        └── role:"assistant" ...... content blocks: text | thinking | tool_use | image
                                    + state (stop reason) + usage (model, tokens)
```

## On disk

Threads live as individual JSON files in one flat directory, named
`<thread-id>.json` where the id is `T-` followed by a UUID-shaped string
(e.g. `T-0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001`). The default root is
`~/.local/share/amp/threads`; txcript's `AmpStore::default_root` honors
`AMP_THREADS_DIR` first, then `XDG_DATA_HOME` (`$XDG_DATA_HOME/amp/threads`,
non-Windows only), then falls back to `~/.local/share/amp/threads`.

Discovery lists `*.json` in that directory and does a shallow parse of each
file: the `v` key (Amp's revision counter, bumped on every write) doubles as
the format sniff, so stray JSON that happens to live there is skipped rather
than fatal, as are unreadable files. A separate `~/.amp/` directory holds
auxiliary state (per-thread `file-changes/<T-id>/` snapshots, `history.jsonl`,
credentials) — none of it is transcript data and txcript ignores it.

## Dissection of a transcript

Amp already follows the Anthropic messages convention, so messages map 1:1
onto txcript's `Common` model with no synthesis or splitting.

| Their name | What it is | Maps to |
|---|---|---|
| thread (the document) | `{v, id, created, title, env, messages, …}` | `Transcript<Amp>`; everything but `messages` rides in `Thread::extra` |
| `id`, `created`, `title` | thread id, epoch-ms creation time, auto title | `Meta::id`, `Meta::timestamp`, `Meta::title` |
| `env.initial.trees[0]` | workspace: `file://` URI + git `repository.ref` | `Meta::cwd` (percent-decoded), `Meta::git_branch` |
| `env.initial.platform` | client kind and version | `Meta::cli_version` |
| message, `role: "user"` | a prompt (`meta.sentAt` epoch ms) or a tool-result carrier (no `sentAt`) | `Message { role: User }` |
| message, `role: "assistant"` | a model turn with `state` and `usage` | `Message { role: Assistant, model, stop_reason, usage }` |
| `state` | `{type: complete\|streaming\|cancelled, stopReason?}` | `StopReason` (`cancelled` → `Aborted`; `streaming` → none) |
| `usage` | `model`, token counts, `timestamp` (newer files) | `Message::model`, `Usage`, `Message::timestamp` |
| block `text` / `thinking` / `image` | `thinking` carries `signature` + `provider`; image `source.mediaType` is camelCase | `Block::Text` / `Block::Thinking` / `Block::Image` |
| block `tool_use` | `{id, name, input, complete}` | `Block::ToolUse`, tool name normalized (below) |
| block `tool_result` | `{toolUseID, run: {status, result\|error, reason, progress, trackFiles}}` | `Block::ToolResult` paired by `toolUseID` |

Ordering is the array order; there is no threading or parent-pointer graph in
local files. Tool calls sit on assistant messages and their results on the
*next user message*, paired by `toolUseID`. Timestamps are sparse: user
prompts carry `meta.sentAt`, newer assistant turns carry `usage.timestamp`
(RFC 3339), and everything else — notably tool-result carriers — inherits the
last seen timestamp. Tool names span two eras, both normalized to the
Claude-canonical spelling: legacy `Bash{cmd,cwd}`, `Read{path,read_range}`,
`edit_file`, `create_file`, `glob{filePattern}`, `read_web_page` vs modern
`shell_command{command,workdir}`. `read_range: [first,last]` converts to
`offset`/`limit`; Amp-only tools (`painter`, `finder`, `web_search`, …) land
in `Tool::Raw` untouched. `run.status` of `done` maps to a normal result
(string → text, anything else → JSON), while `error`, `cancelled`, and
`rejected-by-user` all collapse to an error-flagged text result.

A minimal synthetic thread, shaped like the real files:

```json
{
  "v": 42,
  "id": "T-0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001",
  "created": 1768178184664,
  "title": "Fix the off-by-one",
  "agentMode": "smart",
  "env": { "initial": { "trees": [{ "uri": "file:///Users/dev/proj",
             "repository": { "ref": "refs/heads/main", "type": "git" } }],
           "platform": { "client": "CLI", "clientVersion": "0.0.1768178000-gaaaaaa" } } },
  "messages": [
    { "role": "user", "messageId": 0, "meta": { "sentAt": 1768178271390 },
      "content": [{ "type": "text", "text": "fix the loop bound" }] },
    { "role": "assistant", "messageId": 1,
      "content": [{ "type": "tool_use", "complete": true, "id": "toolu_01",
                    "name": "Bash", "input": { "cmd": "cargo test", "cwd": "/Users/dev/proj" } }],
      "state": { "type": "complete", "stopReason": "tool_use" },
      "usage": { "model": "claude-opus-4-5-20251101", "inputTokens": 12, "outputTokens": 80,
                 "cacheReadInputTokens": 3400, "cacheCreationInputTokens": 900,
                 "maxInputTokens": 168000, "totalInputTokens": 4312 } },
    { "role": "user", "messageId": 2,
      "content": [{ "type": "tool_result", "toolUseID": "toolu_01",
                    "run": { "status": "done", "result": { "output": "ok\n", "exitCode": 0 } } }] }
  ]
}
```

## Caveats

- **The local directory is a legacy artifact.** Current Amp CLI versions are
  server-authoritative: they neither read nor write `threads/` (verified by
  bisection — a file placed there is invisible to `amp threads list`). Only
  era-matched versions (`@sourcegraph/amp` ≤ early 2026) resume these files
  natively, so txcript refuses to *continue* a session into Amp.
- **Version drift.** Observed files span CLI `0.0.1768…` (Jan 2026) through
  `0.0.1773…` (Mar 2026) and one `2.1.x` client. Older files lack
  `usage.timestamp`; bookkeeping keys (`meta`, `readAt`, `protocolMessageID`)
  differ across eras. The codec accepts all of them; unknown top-level keys,
  block kinds, and roles (e.g. shared-thread `"parent"` records) survive
  losslessly in the native body but carry nothing into `Common`.
- **Round-trip lossiness through `Common`** (native → Common → native):
  `run.progress`/`trackFiles`/`~debug`, `userState`, `fileMentions`,
  `turnElapsedMs`, `usage.credits`; `cancelled`/`rejected-by-user` statuses
  collapse to `is_error` text; a stateless assistant renders as `end_turn`.
- **Hostile input.** Discovery skips non-thread JSON; a foreign session id is
  deterministically rewritten (UUIDv5) into a valid `T-…` id before it can
  name a file, and ids are path-safety-checked before writing.

## References

- Amp manual, https://ampcode.com/manual (fetched 2026-08-10): documents
  threads as a product concept only — no storage location, schema, or export
  format is published. This document is reverse-engineered from observed
  local sessions and the txcript implementation.
- Authoritative mapping: `src/harness/amp.rs` (module docs list every known
  representational loss) and `tests/integration/amp.rs` (anonymized fixture
  shaped like a real legacy file).
- Last verified: 2026-08-10, against src/harness/amp.rs and real local sessions.
