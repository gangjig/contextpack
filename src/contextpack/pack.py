"""Pack context items into a token budget, with a manifest.

An agent's context is assembled from pieces with very different
value: a pinned system prompt, the current task, a huge tool result,
yesterday's conversation, a retrieved doc. When the window is too
small for all of it, *something* gets dropped — the only question is
whether the choice is explicit and auditable, or whatever the string
concatenation happened to do.

`contextpack` makes the choice explicit:

* Every item has a `priority` (higher survives longer), may be
  `pinned` (kept verbatim, always — even if pinned items alone exceed
  the budget, which the manifest then flags), and may be
  `truncatable` (kept as the longest prefix that fits, with a
  visible truncation marker).
* Selection runs pinned-first, then by descending priority, ties in
  original order. **Rendering is always in the original input order** —
  selection decides *whether* an item appears, never *where*.
* Every decision lands in a manifest: per item, `kept` / `truncated`
  / `dropped` with its original and kept token counts, plus totals.
  If a run later behaves as if it never saw the doc you retrieved,
  the manifest tells you whether the doc was ever in the context.

Token counting defaults to a chars-per-token estimate (4, the usual
English-prose heuristic) and is injectable: pass any
`text -> int` callable to use a real tokenizer.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

PathLike = Union[str, Path]

TRUNCATION_MARKER = "\n[... truncated]"
DEFAULT_CHARS_PER_TOKEN = 4

TokenCounter = Callable[[str], int]


def estimate_tokens(text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    if chars_per_token <= 0:
        raise ValueError("chars_per_token must be positive")
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)


@dataclass(frozen=True)
class Item:
    name: str
    text: str
    priority: int = 0
    pinned: bool = False
    truncatable: bool = False

    @classmethod
    def from_dict(cls, data: dict, where: str = "item") -> "Item":
        if not isinstance(data, dict):
            raise ValueError(f"{where}: item must be a JSON object")
        for name in ("name", "text"):
            if name not in data:
                raise ValueError(f"{where}: item is missing {name!r}")
        if not str(data["name"]):
            raise ValueError(f"{where}: item 'name' must not be empty")
        priority = data.get("priority", 0)
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError(f"{where}: 'priority' must be an integer")
        return cls(
            name=str(data["name"]),
            text=str(data["text"]),
            priority=priority,
            pinned=bool(data.get("pinned", False)),
            truncatable=bool(data.get("truncatable", False)),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "text": self.text,
            "priority": self.priority,
            "pinned": self.pinned,
            "truncatable": self.truncatable,
        }


def load_items(path: PathLike) -> list[Item]:
    with Path(path).open(encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: items file must be a non-empty JSON list")
    items = [
        Item.from_dict(entry, where=f"{path} item {index + 1}")
        for index, entry in enumerate(data)
    ]
    _check_unique(items)
    return items


def _check_unique(items: list[Item]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.name in seen:
            raise ValueError(f"duplicate item name {item.name!r}")
        seen.add(item.name)


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    status: str  # kept | truncated | dropped
    tokens: int  # tokens in the original item
    kept_tokens: int  # tokens actually included (0 when dropped)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "tokens": self.tokens,
            "kept_tokens": self.kept_tokens,
        }


@dataclass(frozen=True)
class PackResult:
    text: str
    entries: tuple[ManifestEntry, ...]
    budget_tokens: int
    used_tokens: int
    over_budget: bool  # pinned items alone exceeded the budget

    def manifest(self) -> dict:
        counts = {"kept": 0, "truncated": 0, "dropped": 0}
        for entry in self.entries:
            counts[entry.status] += 1
        return {
            "metric": "contextpack",
            "budget_tokens": self.budget_tokens,
            "used_tokens": self.used_tokens,
            "over_budget": self.over_budget,
            "counts": counts,
            "items": [entry.to_dict() for entry in self.entries],
        }

    def entry_for(self, name: str) -> ManifestEntry:
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise KeyError(name)


def _longest_fitting_prefix(
    text: str, remaining: int, count: TokenCounter
) -> Optional[str]:
    """The longest prefix of `text` that fits `remaining` tokens once
    the truncation marker is appended, or None if even the marker
    alone does not fit."""
    if count(TRUNCATION_MARKER) > remaining:
        return None
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count(text[:mid] + TRUNCATION_MARKER) <= remaining:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return None
    return text[:lo] + TRUNCATION_MARKER


def pack(
    items: list[Item],
    budget_tokens: int,
    token_counter: Optional[TokenCounter] = None,
) -> PackResult:
    """Select and render `items` under `budget_tokens`.

    Selection order: pinned items first (original order), then the
    rest by descending priority with original order breaking ties.
    Rendering order: always the original input order.
    """
    if budget_tokens < 0:
        raise ValueError("budget_tokens must be non-negative")
    _check_unique(items)
    count = token_counter or estimate_tokens

    indexed = list(enumerate(items))
    selection_order = sorted(
        indexed,
        key=lambda pair: (
            0 if pair[1].pinned else 1,
            -pair[1].priority,
            pair[0],
        ),
    )

    remaining = budget_tokens
    outcomes: dict[int, tuple[str, str, int]] = {}  # index -> (status, rendered, kept_tokens)
    over_budget = False
    for index, item in selection_order:
        tokens = count(item.text)
        if item.pinned:
            outcomes[index] = ("kept", item.text, tokens)
            remaining -= tokens
            if remaining < 0:
                over_budget = True
            continue
        if tokens <= remaining:
            outcomes[index] = ("kept", item.text, tokens)
            remaining -= tokens
        elif item.truncatable:
            truncated = _longest_fitting_prefix(item.text, remaining, count)
            if truncated is None:
                outcomes[index] = ("dropped", "", 0)
            else:
                kept = count(truncated)
                outcomes[index] = ("truncated", truncated, kept)
                remaining -= kept
        else:
            outcomes[index] = ("dropped", "", 0)

    entries: list[ManifestEntry] = []
    rendered: list[str] = []
    used = 0
    for index, item in indexed:
        status, text, kept_tokens = outcomes[index]
        entries.append(
            ManifestEntry(
                name=item.name,
                status=status,
                tokens=count(item.text),
                kept_tokens=kept_tokens,
            )
        )
        used += kept_tokens
        if status != "dropped":
            rendered.append(text)
    return PackResult(
        text="\n\n".join(rendered),
        entries=tuple(entries),
        budget_tokens=budget_tokens,
        used_tokens=used,
        over_budget=over_budget or used > budget_tokens,
    )
