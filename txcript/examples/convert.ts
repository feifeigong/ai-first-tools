// Convert a local session between harnesses using the WASM module.
//
//   bun run build            # produce ./pkg (once, or after Rust changes)
//   bun examples/convert.ts <file> <from> <to>
//
// e.g. bun examples/convert.ts ~/.codex/sessions/.../rollout-*.jsonl codex claude_code

import { convert, toCommon, harnesses } from "../pkg/txcript.js";
import { readFileSync } from "node:fs";

const [file, from, to] = process.argv.slice(2);
if (!file || !from || !to) {
  console.error("usage: bun examples/convert.ts <file> <from> <to>");
  console.error("harnesses:", harnesses().join(", "));
  process.exit(1);
}

const input = readFileSync(file, "utf8");

const common = JSON.parse(toCommon(input, from));
console.error(`${common.messages.length} messages in session ${common.meta.id}`);

process.stdout.write(convert(input, from, to));
