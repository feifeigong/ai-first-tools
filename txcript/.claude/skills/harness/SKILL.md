---
name: harness
description: Integrate a new AI coding-agent harness into txcript — native Body types, Codec, TextCodec, Store, wiring, and tests. Use when asked to add or integrate a new harness or transcript format. Takes the harness name, its format docs (URL or path), and one real local session id to anchor implementation and verification on.
argument-hint: <name> <docs-url-or-path> <sample-session-id>
---

# Integrate a new harness

You are adding a harness to txcript, the transcript converter in this repo. The
work is one flat file `src/harness/<name>.rs` plus wiring and tests, but the
quality bar is set by two fidelity contracts (below) and by the fact that the
output must actually *resume* in the native app — a session that loads but
shows an empty conversation is a failed integration.

## Inputs

`$ARGUMENTS`: `<name> <docs> <sample-session-id>`

- `name` — the harness (e.g. `gemini`, `amp`). Derive the snake_case id from it.
- `docs` — URL or file path describing the native transcript format.
- `sample-session-id` — a real session of that harness on this machine. This is
  your ground truth. If any input is missing, ask before starting.

## The two fidelity contracts (non-negotiable, from `src/lib.rs`)

1. **Native ↔ disk is record-lossless.** The `Body` holds a faithful typed
   representation; `Store`/`TextCodec` round-trip it without loss. This is
   value-level, not byte-level: `serde_json` is built without `preserve_order`,
   so key order canonicalizes — tests assert record equality, never string
   equality of the file.
2. **Through `Common` is semantically lossless.** `to_common` may canonicalize
   representation (so the thread works in another harness) but must never
   discard what a same-harness round trip needs. The testable form is the
   fixpoint: `to_common(from_common(c)) == c` for any `c` in the
   harness-representable subset of `Common`.

Corollary: `from_common` must be **pure and deterministic** — synthetic ids are
UUIDv5 over a fixed namespace and stable keys like `"{session_id}:{i}:{j}"`,
never `Uuid::new_v4()` (sole exception: generating a session id when `meta.id`
is empty), never clock reads.

## Phase 0 — Recon: the bytes are the spec

Before writing any Rust:

1. Read the docs at `<docs>`.
2. Find the sample session on disk. Probe the harness's storage root
   (`~/.<name>/…`, XDG data dirs, an SQLite DB, app-support dirs) until you
   locate the file/rows for `<sample-session-id>`.
3. Dump the raw session into the scratchpad. Catalog **every** record/blob kind
   you observe: which carry conversation (user/assistant/tool records), which
   are bookkeeping (headers, token counts, snapshots, titles, model changes),
   which are opaque (binary, protobuf).
4. Check how the native app resumes a session (CLI flag, id format, sidecar
   files it validates). The consumer defines correctness, not the schema.
5. **Interrogate the consumer by bisection.** Find the harness's cheapest
   read-only replay of a session (`<name> export`, `sessions list`, a
   `--print` resume) and use it as a load oracle: copy the sample under a
   fresh id, then delete files/records until it stops loading. What survives
   deletion is bookkeeping; what breaks the load is the regeneration contract
   for `from_common` — learned before writing any code, at zero model cost.
6. **Mint the bytes the sample lacks.** One session won't cover every record
   kind you must emit (file edits, images, errored calls, aborts). Don't
   guess from docs — run the harness itself headlessly in a scratch dir with
   prompts engineered to exercise each gap, and probe its input flags (a
   `--prompt-json`-style flag reveals content-block encodings). The same
   trick answers optionality questions: to learn whether the native parser
   treats a field as optional, load a session without it.
7. For multi-file/dual-log formats, write down the **exclusive carrier** of
   each semantic field: timestamps, images, or stop reasons may exist *only*
   in the display log while reasoning tokens exist *only* in the model log.
   `to_common` is then a join across carriers and `from_common` a fan-out —
   knowing the carrier map is most of the codec design.

Where docs and bytes disagree, model the bytes. Keep the dump — it becomes your
test fixture material and the final verification anchor. Copy the sample
session out of the live root NOW: `save()` derives its path from `Meta`, so
converting a session back into its source harness reuses the original id and
silently overwrites your ground truth.

## Phase 1 — Choose the Body shape

Pick the closest existing codec as your reference and re-read it before
implementing (don't work from memory of it):

| Native format | Reference | Body pattern |
|---|---|---|
| JSONL, one envelope kind | `codex.rs` | Single `Line { timestamp, type, payload: Value, #[serde(flatten)] extra }` |
| JSONL, a few typed kinds | `claude_code.rs`, `pi.rs` | Enum with manual serde via `From<Value>` dispatch on the `type` tag; parse failure → `Other(Value)`; `tagged()` helper re-inserts the tag on render |
| One JSON export document | `opencode.rs` | Body = the harness's own export/import shape; typed two-level envelope, everything inside stays `Value`, navigated with `.get()` |
| SQLite with opaque blobs | `cursor.rs` | Body = raw rows (`Vec<u8>` blob bytes with hex serde + meta rows); losslessness at the blob level; only *parse* what you understand |
| Session directory, multiple logs | `grok.rs` | Body = struct of per-file fields (typed model log, raw `Vec<Value>` display/telemetry logs, `Option<Value>` sidecars); "text" is a JSON bundle of the directory |
| Sibling of an existing harness | `campfire.rs` | Thin delegate: reuse the donor's `pub(crate)` helpers, change only identity and storage root |

Details and per-harness idioms: read `references/patterns.md` in this skill
directory now.

## Phase 2 — Native record rules

- Type only what the codec must interpret; keep messy payload unions as raw
  `Value` inside a typed envelope.
- Every typed record struct: `#[serde(flatten)] extra: Map<String, Value>` for
  unknown keys, and `#[serde(default, skip_serializing_if = "Option::is_none")]`
  on every optional field — absent must not round-trip as `null`.
- The type tag lives **outside** the struct (stripped on parse, re-inserted on
  render), or it duplicates into `extra`.
- Any classification/parse failure demotes to a raw-`Value` variant
  (`Record::Other(v)`) — never an error, never a dropped line. One corrupt line
  must not sink the session (`jsonl::parse` already skips unparseable lines for
  the line-based path).
- Do NOT put `deny_unknown_fields` on harness record types. It exists only on
  the canonical tool-arg structs in `common.rs`, where it forces the lossless
  `Tool::Raw` fallback.

## Phase 3 — Codec

### to_common

- **Claude Code is the canonical convention.** Write a
  `normalize_tool(name, input)` that maps native tool names and argument keys
  onto it (`bash`→`Bash`, `path`→`file_path`, …), then call
  `Tool::from_canonical`. Its `deny_unknown_fields`→`Raw` fallback is the
  safety net — never bypass it, never pre-drop keys. `mcp__*` passes through.
  Write `denormalize_tool` at the same time; they must be a real inverse pair,
  including shape changes (e.g. pi's multi-hunk `edit` → `Edit`/`MultiEdit` by
  hunk count).
- Tool results ride on `Role::User` messages (Anthropic convention). Errored
  calls → `is_error: true`; in-flight calls → `ToolUse` with no result.
- Skip bookkeeping records and harness-injected scaffolding (environment
  preambles, `<user_query>`-style wrappers — strip on read, re-wrap on write).
  Skip empty/whitespace-only blocks and messages that end up empty. Unknown
  block types drop from Common — they still live in the native body.
- Turn-level attribution (model, usage, stop reason) often lives in bookkeeping
  records far from the message: do a stateful pass with per-turn maps and
  backfill onto the right assistant message (typically the last text message of
  the turn).
- Dual-log formats (protocol log + display log): pick the canonical record per
  kind, mark fallback mirrors, dedup by call id in a post-pass so file order
  doesn't matter.
- Pairing without ids: key on serialized semantic content, tolerate both
  arrival orders, use a deterministic synthetic id as last resort.
- Timestamps: parse per-record with fallback to `meta.timestamp`; never error.

### from_common

- Regenerate **every field the native app validates on resume — even as
  explicit `null`** (codex refuses sessions missing `model_provider`/
  `base_instructions` keys). Regenerate both logs of a dual-log format, and any
  internal structures the app needs (Cursor's protobuf turn graph, sidecar
  `meta.json`). The failure mode here is *silent*: the app starts a fresh or
  empty session. Only end-to-end resume testing catches it.
- **Write only field shapes you have observed the native app write.** This is
  the *loud* failure mode, dual to the silent one: native parsers are strict,
  and one field of an unobserved type fails the WHOLE session load ("invalid
  type: sequence, expected a string"). Structural pass-through is the
  lossless instinct for reading and exactly wrong for writing — where Common
  is richer than the observed slot (structured `ToolOutput::Json` into a
  string field, an image block into a text-only log), flatten to the observed
  shape (block arrays → joined text, other JSON → compact string, image →
  its display-log carrier plus a placeholder) and document the loss.
- Carry a `tool_use_id → native tool name` map while emitting tool calls so
  redundant result fields can be reconstructed; give orphans a fallback.
- Fabricate required-but-derivable fields plausibly (provider from a model-id
  prefix, zero cost objects, `totalTokens`) and comment that they are
  best-effort historical reconstruction.
- Option-vs-zero trap: never serialize a default that parses back as
  `Some(default)` (e.g. omit an all-zero cache object entirely).
- Some Common detail may have no native slot (thinking signatures,
  `replace_all`, `StopReason::Other`). Accept the loss, document it in the
  module doc, and keep the fixpoint fixture inside the representable subset.

### Meta

`meta_from_records`: per-field fallback chains with explicit keep-first or
last-wins semantics (e.g. latest `model_change` wins; `custom-title` beats
summary). Filter placeholder titles. Leave `id` empty when the text has none —
the Store fills it from the filename/row. Timestamp fallback: `Utc::now()`.

## Phase 4 — TextCodec + Store

- `TextCodec` is pure text↔records, zero I/O — it is the WASM boundary. For a
  DB-backed harness, "text" is a JSON dump of the Body (binary as hex), not
  anything the native tool emits; it must round-trip to an identical Body.
- `Store`: `default_root()` returns `Option<Self>` honoring env overrides then
  `$HOME` paths (match the pattern in `pi::resolve_sessions_dir`). `discover()`
  is tolerant: missing root → `Ok(vec![])`, unreadable files silently skipped,
  and **sniff the format** (e.g. first record must be the session header) —
  extension alone doesn't identify a harness. `load()` backfills an empty
  `meta.id` from the file stem (`jsonl::file_id`). `save()` derives a
  deterministic path from `Meta` — copy the native app's directory encoding
  *exactly* (Claude maps both `/` and `.` to `-`; pi wraps `--{cwd}--`; Cursor
  uses `md5(cwd)`). `fingerprints()` is cheap: `"{mtime_nanos}:{len}"` or a
  `MAX(time)` query; failures → empty string, never an error.
- New native dependency (SQLite etc.): make it a cargo feature (`dep:` only),
  keep the codec and Body compiling featureless, and stub the Store without the
  feature (empty discover, `Unconvertible` load/save). Open another tool's DB
  `READ_ONLY`; prefer delegating writes to the harness's own CLI importer if
  one exists (`opencode import` pattern) over reverse-engineering schema
  defaults.

## Phase 5 — Wiring checklist

Every item, in order; the exhaustive matches make most omissions compile
errors:

1. `src/harness/<name>.rs` — the whole harness, one flat file, module doc
   explaining format + known losses.
2. `src/harness/mod.rs` — `pub mod <name>;`
3. `src/transcript.rs` — `HarnessId` variant, `ALL` array (bump its length),
   `as_str`, `FromStr` with friendly aliases.
4. `src/bin/cli.rs` — `resume_command` default, a `discover_all` block, a
   `load_common` arm, a `save_target` arm.
5. `src/wasm.rs` — both dispatch matches (`parse_to_common`,
   `render_from_common`) and the doc-comment harness list.
6. `Cargo.toml` — feature entry if a new dep; keep it out of the `wasm` build.
7. `README.md` — supported-harness list, string id, WASM text-format note.
8. `tests/integration/<name>.rs` (declared in `tests/integration/main.rs`),
   a new hop in `tests/integration/cross_harness.rs`, and a new
   `assert_fixpoint` line in `tests/integration/properties.rs` — see
   `tests/README.md` for the taxonomy.

Repo style: hierarchical imports — import modules and qualify (`common::Tool`,
`jsonl::parse`), never flatten items to the crate root. Clippy pedantic is on
and `unwrap/expect/panic` are **denied** in `src/` (allowed in tests via the
file-top `#![allow]`).

## Phase 6 — Tests

Standard invariants, one test each, named as behavior sentences. Fixtures are
inline `json!` + `tempfile` — no checked-in fixture files. Build the native
fixture from the *real* sample session's shapes (anonymized), covering every
record kind you cataloged in Phase 0, including one unmodeled record that must
survive.

1. `store_round_trip_is_lossless_on_disk` — load→save→load, record equality
   including unknown records; assert the save path shape.
2. `discover_extracts_metadata` — every populated `Meta` field.
3. `to_common_…` — faithful extraction: typed tools with renamed keys,
   bookkeeping skipped, result pairing, usage/stop backfill, message count
   asserted exactly.
4. `codec_fixpoint_through_common_loses_nothing` —
   `to_common(from_common(c)) == c`. Shape the Common fixture at the harness's
   native granularity (message grouping, which fields are mandatory, result
   timestamps) — this is the direction that holds; `from_common ∘ to_common`
   need not be byte-identical.
5. `from_common_is_deterministic` — two runs serialize identically.

Plus one test per quirk you handled (error results, pending calls, legacy
shapes, format sniffing), and extend the `cross_harness.rs` chain with the new
harness so the block signature survives the extra hop. Store tests that need
the native dep go `#[cfg(feature = …)]` inside the gated module against a real
temp DB — never mocks.

## Phase 7 — Verification gates

All must pass before you call it done:

1. `cargo test` and `cargo test --no-default-features`.
2. `cargo clippy --all-targets` — pedantic-clean, no `unwrap`/`expect` in
   `src/`.
3. **Real-session anchor**: load `<sample-session-id>` through the new Store,
   `to_common`, and inspect the conversation end to end — no dropped turns, no
   scaffolding leaking in as user text, tools typed where expected. Then run
   the fixpoint on this real transcript, and convert it to `claude_code` and
   back, checking the cross-harness block signature.
4. **Resume in the native app** (the only gate that catches
   missing-required-header and missing-display-log bugs): write the converted
   session with `txcript continue <id> --with <name> --no-resume` (or `--out`
   plus a copy into the live root), then resume it with the harness's own CLI
   and confirm the conversation renders and the session continues. Also do the
   reverse direction: sample → `claude_code`, resume with `claude --resume`.
   Two rules learned the hard way:
   - **The sample round trip is the weakest resume test** — it only exercises
     the subset of Common the sample happens to use, and it passes trivially.
     Also convert a *kitchen-sink* source: a real session from the richest
     other harness (or a synthetic Common) carrying structured JSON tool
     results, images, thinking, errored calls, and an aborted turn. Write-side
     shape bugs (the "loud" from_common failure) only surface here.
   - **Verification writes get a fresh session id** (set `meta.id` before
     `from_common`) so they can't collide with — and overwrite — real
     sessions; clean them out of the live roots afterward.
   Order the resume work by cost: the read-only export/list oracle first
   (validates the display log), then one headless `-p`-style resume turn
   (validates the model log actually carries the context), then the TUI.
5. README and module docs updated; known representational losses documented in
   the module doc.

Report the result with: record kinds handled vs passed-through, tool mappings,
known losses, and the resume verification outcome for both directions.
