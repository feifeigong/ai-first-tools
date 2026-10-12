# campfire

Campfire is a coding-agent product that embeds pi's open-source coding agent
as a library (`@earendil-works/pi-coding-agent`) rather than implementing its
own harness. pi ships a branding indirection for exactly this — an embedder
can rename the app and its config dot-directory — so Campfire's sessions are
byte-identical pi v3 JSONL, just written under a Campfire-branded home. This
doc's provenance is therefore inherited: the **format** is specified by pi's
open-source code (see [pi.md](pi.md)); the **Campfire-specific bits** — root
directory and env prefix — are verified against txcript's parser and real
local sessions.

```
~/.campfire/agent/sessions/            Campfire-branded home
└── --Users-alice-src-myproj--/        …everything below identical to pi:
    └── <timestamp>_<uuid>.jsonl       header + id/parentId tree of records
```

## On disk

Same scheme as pi with the prefix swapped (see
`pi::resolve_sessions_dir(".campfire", "CAMPFIRE")`):

1. `CAMPFIRE_CODING_AGENT_SESSION_DIR` — sessions dir verbatim;
2. `CAMPFIRE_CODING_AGENT_DIR` — agent dir, sessions in `<dir>/sessions`;
3. default `~/.campfire/agent/sessions`.

Directory encoding (`--…--` per cwd), file naming
(`<timestamp>_<uuid>.jsonl`), and discovery are pi's, reused verbatim by
`CampfireStore`.

## Dissection of a transcript

Identical to pi in every record type, field name, and Common mapping — the
`session` header, the `message` tree with `user` / `assistant` /
`toolResult` / `bashExecution` roles, `custom_message`, and the bookkeeping
types. See [pi.md](pi.md#dissection-of-a-transcript) for the full table and
example.

| Their name | What it is | Maps to |
|---|---|---|
| *everything* | pi v3 session records | exactly as in [pi.md](pi.md) |

In txcript, `Campfire` is a distinct harness marker sharing pi's native
`Record` body; its codec and store delegate to the `pub(crate)` helpers in
`src/harness/pi.rs`.

## Lineage

Identical to pi: `parentSession` in the header resolves to a Fork `Meta.lineage`. See
[pi.md](pi.md#lineage).

## Caveats

All of pi's caveats apply unchanged (branch flattening, Common lossiness,
hostile-input handling). One addition: because the two harnesses share one
format, a file is attributed to a harness purely by which root it was
discovered under — a pi file dropped into `~/.campfire/agent/sessions/`
loads as a Campfire session, and vice versa.

## References

- The format is pi's; see the pinned upstream permalinks in
  [pi.md](pi.md#references), including the branding indirection in
  `packages/coding-agent/src/config.ts` that produces the `.campfire` home
  and `CAMPFIRE_CODING_AGENT_*` env names.

The authoritative txcript mapping is `src/harness/campfire.rs` (a thin
delegate over `src/harness/pi.rs`).

Last verified: 2026-09-26, against src/harness/campfire.rs and real local
sessions.
