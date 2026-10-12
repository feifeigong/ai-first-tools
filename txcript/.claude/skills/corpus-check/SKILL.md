---
name: corpus-check
description: Validate a txcript parsing, discovery, or search change against every real agent session on this machine — old-vs-new parity, no panics, and release-build timings. Use before landing changes to discover(), Store loaders, codecs, or the search index.
argument-hint: [what changed, e.g. "discover() fast path" or "index ordering"]
---

# Corpus check

Unit fixtures cover the shapes we thought of; the ~570 real sessions across
harnesses on this machine cover the shapes that actually exist. Any change to
`discover()`, a `Store` loader, a codec, or `search::Index` gets validated
against the full local corpus before it lands. This was done ad hoc twice
(discover-vs-load meta parity on Jul 6 2026; index determinism on Jul 9 2026)
— this skill is the distilled procedure.

## Procedure

1. **Write a throwaway harness as an example binary** (`examples/`, modeled on
   `examples/search_bench.rs`), not a test — it needs the real home-directory
   corpus, which tests must never touch. Delete it (or leave it untracked)
   when done unless the user wants it kept.
2. **Compare old vs new on identical inputs.** Two options, cheapest first:
   - If the old behavior is reachable from the new code (e.g. full `load()`
     vs the new `discover()` fast path), compare both paths in one binary.
   - Otherwise build a baseline binary from `main` (`git stash` /
     `git worktree`) and diff the two binaries' outputs on the same corpus.
   Parity means field-level equality of the results (`Meta` fields, message
   counts, hit ordering), not just "both succeeded". Report mismatches with
   session id + harness so they can be inspected individually.
3. **Count failures explicitly.** Unreadable stores/sessions are skipped by
   design in `local::sessions()` — capture the skip count and check it didn't
   grow versus baseline. Zero panics is a hard gate (overflow checks are on
   in release for exactly this).
4. **Time it in release.** `--release` only; report per-harness before/after
   wall clock, since the corpus is dominated by one or two harnesses and an
   aggregate number hides regressions in the small ones.

## Known traps (each cost real debugging time)

- **The current session mutates mid-scan.** The session recording this very
  run grows while you read it, so two enumerations differ. Exclude the live
  session id, or scope comparisons with a harness/cwd filter that avoids it
  (`--from <fixture-harness>` was the Jul 9 fix).
- **Bookkeeping-only files have no real timestamp.** Sessions with no
  conversational records fall back to `Utc::now()` for `Meta.timestamp`, so
  they "mismatch" between any two runs. Treat timestamp diffs on such files
  as expected; verify by checking the file has no conversational records
  before calling it a regression.
- **Fixture/synthetic sessions live in the corpus** (greeting fixtures,
  cross-harness duplicates sharing one id). Ties and duplicates are where
  ordering nondeterminism hides — don't dedupe them away when checking
  determinism; run the pass twice and require identical output.

## Report

State: corpus size per harness, parity result (mismatches with ids, or none),
skip/failure counts vs baseline, per-harness timings before/after, and whether
the throwaway harness was deleted or kept.
