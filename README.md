# contextpack

**Assemble LLM context under a hard token budget — with the drop
decisions explicit, and a manifest to prove them.**

Every agent assembles context from pieces of wildly different value:
a system prompt that must never be cut, the current task, a 40,000-
token tool result, yesterday's conversation, a retrieved doc. When
the window is too small for all of it, something gets dropped. The
only question is whether the choice is deliberate and auditable — or
whatever the string concatenation happened to do, discovered weeks
later when the agent "somehow" never saw the doc you retrieved.

`contextpack` makes the choice explicit. Items carry a priority, an
optional `pinned` flag and an optional `truncatable` flag; the
packer selects under your budget and emits a **manifest**: every
item, kept / truncated / dropped, with its token counts.

## Quickstart

```bash
pip install -e .
contextpack demo
```

```
| Item | Status | Tokens | Kept |
|---|---|---:|---:|
| system | kept | 28 | 28 |
| task | kept | 27 | 27 |
| retrieved_doc | kept | 40 | 40 |
| recent_history | kept | 32 | 32 |
| tool_result | **truncated** | 443 | 133 |
| old_history | **dropped** | 48 | 0 |

Budget: 260 tokens; used: 260.
```

Real use, as a library:

```python
from contextpack import Item, pack

result = pack([
    Item("system", SYSTEM_PROMPT, priority=100, pinned=True),
    Item("task", task_text, priority=90),
    Item("tool_result", huge_output, priority=40, truncatable=True),
    Item("history", old_turns, priority=10),
], budget_tokens=8000)

prompt = result.text            # rendered in the original input order
audit = result.manifest()       # who survived, who didn't, and why
```

Or from the shell — the context goes to stdout (or `--out`), a
summary to stderr, the manifest to a file if you ask:

```bash
contextpack pack items.json --budget 8000 --out context.txt --manifest manifest.json
```

## The policies

- **Pinned** items are kept verbatim, always. If pinned items alone
  exceed the budget, they are still kept — a system prompt you
  silently truncated is worse than a budget you knowingly exceeded —
  and the manifest flags `over_budget` (the CLI prints a warning).
- **Priority** decides everything else, highest first; ties keep
  input order. Selection decides *whether* an item appears, never
  *where*: the assembled context is always rendered in the original
  input order, so a last-minute high-priority injection doesn't
  scramble the conversation.
- **Truncatable** items that don't fit whole are kept as the longest
  prefix that does fit, with a visible `[... truncated]` marker —
  the model can see that content was cut, and the manifest records
  how much. If not even the marker fits, the item drops whole.
- Everything else that doesn't fit is dropped whole, and the
  manifest says so, with its full token count as the reason's weight.

**Token counting** defaults to the 4-chars-per-token estimate and is
injectable: pass any `text -> int` callable (a real tokenizer for
your model) to `pack()` and every decision, including truncation
points, uses it.

## Recreate this project from a prompt

> Build a Python package called `contextpack` that assembles LLM
> context under a hard token budget with explicit, auditable drop
> policies. An item has a name, text, integer priority, and optional
> pinned and truncatable flags; items load from a JSON list file with
> validation and unique names. Packing selects pinned items first
> (kept verbatim even if they alone exceed the budget, flagged in the
> output), then the rest by descending priority with input order
> breaking ties; an item that fits is kept, a truncatable item that
> doesn't fit is kept as the longest prefix (found by binary search
> over a pluggable token counter) that fits once a visible
> "[... truncated]" marker is appended, and anything else over
> budget is dropped whole. The assembled context renders in the
> original input order regardless of selection order, and the result
> carries a manifest — per item: name, kept/truncated/dropped status,
> original and kept token counts; plus budget, used total, an
> over-budget flag and status counts — renderable as JSON. The
> default token counter is a configurable chars-per-token estimate,
> replaceable by any text-to-int callable. Provide a CLI (pack an
> items file with --budget, --out, --manifest and --chars-per-token;
> context to stdout, a summary line to stderr) and a demo that packs
> a sample context where a pinned system prompt and the task survive,
> a huge tool result is truncated to land exactly on budget, and old
> history is dropped. Standard library only, with a pytest suite
> covering the priority/pinned/truncation semantics, original-order
> rendering, custom tokenizers, manifest shape, and the CLI.

## Limitations

- **The default counter is an estimate.** 4 chars/token is a fair
  heuristic for English prose and a poor one for code, CJK text or
  dense JSON. Inject a real tokenizer when the budget is a hard
  external limit (an API's actual context window), and keep headroom
  when it is.
- **Truncation is a prefix cut.** It keeps the *start* of a tool
  result; for outputs whose value sits at the end (test summaries,
  error traces), prefer pre-trimming in the harness or a lower
  priority over relying on the prefix.
- **Separator tokens are not counted.** Items are joined with a
  blank line whose cost isn't in the manifest's totals — another
  reason the estimate wants headroom.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
python -m pytest        # 19 tests, fully offline
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Gang Ji.
