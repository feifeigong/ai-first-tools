# Cloud Cowork

`cowork_remote` reads Cowork sessions stored in Claude's cloud (`cse_…` ids),
including sessions Claude presents through a `/chat/…` URL.
It is separate from `cowork`, which reads and writes local Desktop sessions
(`local_…` ids). Cloud sessions are a pull-only source.

## Access

Reuse the signed-in Claude Desktop account on macOS, as with
[Claude Chat](claude-chat.md):

```sh
txcript list --from cowork_remote
txcript view cse_YOUR_SESSION_ID --from cowork_remote
txcript export cse_YOUR_SESSION_ID --from cowork_remote --out task.json
txcript export 'https://claude.ai/chat/YOUR_COWORK_CHAT_UUID' --from cowork_remote --out task.json
txcript continue cse_YOUR_SESSION_ID --from cowork_remote --with claude_code --no-resume
```

`session_…` is accepted as an alias for `cse_…`. Full Cowork URLs, Cowork chat
URLs, and bare version-8 chat UUIDs also load directly without listing sessions
first. Use `--from cowork_remote` for these chat links. Ordinary Claude chats
still use `claude_chat`. An exact title requires explicit cloud discovery.
Message ranges such as `cse_YOUR_SESSION_ID#5-12` work with view, export, crop,
and continue. A crop or continue needs a writable destination.

The active Desktop organization is used by default. The shared
`TXCRIPT_CLAUDE_CHAT_ORGANIZATION_UUID` setting can select another organization;
library callers can also pass it to `CoworkRemoteStore::session_ref`.
Authentication has the same macOS Keychain, cookie encryption, and platform
requirements as Claude Chat. No new login or credential environment variables
are introduced.

Aggregate local discovery, search indexing, and `txcript list` without
`--from cowork_remote` do not contact this source. MCP listing also refuses
cloud enumeration; `read_session` can read an explicitly selected source and
full id. Store construction does not list sessions.

## Library and wire format

The `cowork_remote` Cargo feature, enabled by default, reuses the `claude_chat`
transport. The native codec remains available without network features and
through WASM. Consumers use the ordinary `Store` and `Codec` traits:

```rust,no_run
use txcript::{Codec, Store};
use txcript::harness::cowork_remote::{CoworkRemote, CoworkRemoteStore};

# fn main() -> txcript::Result<()> {
let store = CoworkRemoteStore::from_desktop()?;
let reference = store.session_ref("cse_YOUR_SESSION_ID", None)?;
let native = store.load(&reference)?;
let common = CoworkRemote::to_common(&native)?;
# Ok(())
# }
```

The reader uses Claude's private code-session API on `https://claude.ai`:

- `GET /v1/code/sessions?tags=cowork-remote&limit=200`
- `GET /v1/code/sessions/{id}`
- `GET /v1/code/sessions/{id}/events?limit=500&sort_order=asc`

Both lists follow `next_cursor`. Cowork tags distinguish these sessions from
Claude Code sessions served by the same API. Organization ids and session ids
are validated before requests. Requests carry the existing Desktop cookies
and the code-session API's organization and version headers. Redirects are
disabled; no provider writes, deletes, launches, or resumes occur.

For a Cowork chat UUID, the reader first requests an existing-only snapshot
from `POST /claudeai-rpc/anthropic.bard.api.v1alpha.ConversationService/StreamTimeline`.
This is a read RPC using Connect JSON framing. It stops at the initial full
snapshot and never calls mutation or view-reporting methods. A version-8 UUID
only selects this lookup: the returned chat id must match, `CoworkSessionMeta`
must identify it as a presented Cowork session, and `WorkspaceUpgradeState`
must supply one unambiguous Cowork session id. The ordinary paged event reader
then reads that backing session. A workspace attached to an ordinary chat does
not qualify. Failed lookups do not fall back to account enumeration.

A native document contains the complete detail response under `session` and
the ordered event envelopes under `events`. Unknown fields survive native
round trips. Complete top-level SDK user and assistant messages use the
Claude Code block mapping, including thinking, tools, tool results, inline
images, model, usage, and stop reason. Event timestamps fill missing message
timestamps. Repeated identical event ids convert once; conflicting duplicates
and malformed messages fail explicitly.

Chat-link reads additionally retain the complete mapping snapshot under
`$txcript_chat_snapshot`. Metadata and Common messages use the canonical
`cse_…` id, so the original URL and the chat URL identify the same session.

## Boundaries

- Explicit loads download uploaded attachments and files presented by
  `Artifact`, `SendUserFile`, and `present_files`. Bytes, names, and MIME types
  are preserved as Common artifacts and under `$txcript_files` in native
  exports. VM paths use Claude's session download endpoint; file UUIDs use its
  organization file endpoint. A remote path is never opened on the host.
- File downloads are bounded to 64 MB each and 128 MB per session. A missing
  or inaccessible referenced file fails the read with its filename. Arbitrary
  working-directory files and nested subagent files are not collected.
- Path-based downloads retrieve the current file contents, not historical
  versions. Repeated presentations of a path share the downloaded contents.
- The remote working directory stays in the native response; Common does not
  advertise it as a usable directory on the recipient's machine.
- Streaming deltas, control events, and nested subagent messages stay in the
  native document. Common includes complete top-level messages only. A live
  turn can therefore be absent until its complete message is persisted.
- The paged read is not an atomic snapshot of an actively changing session.
  Malformed or looping pagination, failed pages, and page/row/byte limits
  return an error rather than a successful partial transcript.
- The chat URL is an entry point to its backing Cowork events. This does not
  import independent ordinary-chat continuations or the chat interface's
  display-only grouping. A chat without a verified Cowork mapping is refused.
- `from_common`, `save`, `delete`, and continuing into `cowork_remote` are
  refused. Pull into local `cowork` or another writable harness instead.
- These private endpoints and Desktop authentication can change independently
  of txcript. Protocol failures are reported to the explicit caller.

## Evidence

Protocol paths, headers, id aliases, detail wrappers, and event envelopes were
inspected in the installed Claude Desktop app's shipped web client on
2026-09-28. Contract tests use synthetic sessions and a local HTTP server;
no customer transcripts or credentials are included in fixtures.

Related reports: [missing cloud sessions (#61)](https://github.com/skillsynchq/txcript/issues/61)
and [missing Cowork files (#62)](https://github.com/skillsynchq/txcript/issues/62).

