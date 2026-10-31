# Changelog

## 0.1.0 — 2026-10-31

- **Initial release: context assembly under a token budget, with a
  decision manifest.** Items (name, text, priority, `pinned`,
  `truncatable`) load from a JSON file with validation and unique
  names. `pack()` selects pinned items first — kept verbatim even
  past the budget, which the manifest flags — then by descending
  priority with input order breaking ties; truncatable items are cut
  to the longest fitting prefix (binary-searched against the token
  counter) with a visible `[... truncated]` marker, and the rest
  drop whole. Rendering is always in the original input order. The
  manifest records kept / truncated / dropped per item with token
  counts, totals and an over-budget flag. Token counting defaults to
  a configurable chars-per-token estimate and accepts any injected
  `text -> int` tokenizer. The CLI packs from the shell (context to
  stdout or `--out`, manifest to `--manifest`, summary to stderr);
  the demo lands exactly on its 260-token budget with the tool
  result truncated and old history dropped. Standard library only.
