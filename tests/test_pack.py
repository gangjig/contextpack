"""Packing: selection by priority, pinned guarantees, truncation,
original-order rendering, injectable tokenizers, the manifest."""

import math

import pytest

from contextpack.pack import Item, estimate_tokens, load_items, pack


def item(name, text, **kwargs):
    return Item(name=name, text=text, **kwargs)


def words(n):
    return " ".join(["word"] * n)  # 5n-1 chars -> ceil((5n-1)/4) tokens


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("a" * 10, chars_per_token=3) == math.ceil(10 / 3)
    with pytest.raises(ValueError, match="must be positive"):
        estimate_tokens("x", chars_per_token=0)


def test_everything_fits_and_order_is_input_order():
    items = [
        item("low", words(4), priority=1),
        item("high", words(4), priority=99),
        item("mid", words(4), priority=50),
    ]
    result = pack(items, budget_tokens=1000)
    assert all(e.status == "kept" for e in result.entries)
    # Rendering follows input order, not priority order.
    assert result.text.index("word") >= 0
    positions = [result.text.find(it.text) for it in items]
    assert positions == sorted(positions)
    assert result.used_tokens <= 1000
    assert result.over_budget is False


def test_priority_decides_who_is_dropped():
    keep = item("keep", " ".join(["keep"] * 10), priority=10)  # 13 tokens
    drop = item("drop", " ".join(["drop"] * 10), priority=1)   # 13 tokens
    result = pack([drop, keep], budget_tokens=13)
    assert result.entry_for("keep").status == "kept"
    assert result.entry_for("drop").status == "dropped"
    assert drop.text not in result.text
    assert keep.text in result.text


def test_equal_priority_keeps_input_order_first():
    first = item("first", words(10), priority=5)
    second = item("second", words(10), priority=5)
    result = pack([first, second], budget_tokens=13)
    assert result.entry_for("first").status == "kept"
    assert result.entry_for("second").status == "dropped"


def test_pinned_kept_even_over_budget():
    pinned = item("sys", words(20), pinned=True)  # 25 tokens
    other = item("other", words(4), priority=99)
    result = pack([pinned, other], budget_tokens=10)
    assert result.entry_for("sys").status == "kept"
    assert result.entry_for("other").status == "dropped"
    assert result.over_budget is True
    assert result.used_tokens == 25


def test_pinned_wins_over_truncation():
    big = item("big", words(50), pinned=True, truncatable=True)
    result = pack([big], budget_tokens=5)
    entry = result.entry_for("big")
    assert entry.status == "kept"
    assert entry.kept_tokens == entry.tokens


def test_truncatable_item_is_cut_to_fit():
    big = item("big", "x" * 400, truncatable=True)  # 100 tokens
    result = pack([big], budget_tokens=40)
    entry = result.entry_for("big")
    assert entry.status == "truncated"
    assert entry.tokens == 100
    assert entry.kept_tokens <= 40
    assert result.text.endswith("[... truncated]")
    assert result.text.startswith("x" * 100)
    assert result.used_tokens == entry.kept_tokens


def test_truncatable_with_no_room_is_dropped():
    big = item("big", "x" * 400, truncatable=True)
    result = pack([big], budget_tokens=2)  # marker alone costs 5 tokens
    assert result.entry_for("big").status == "dropped"
    assert result.text == ""


def test_non_truncatable_over_budget_is_dropped_whole():
    big = item("big", "x" * 400)
    small = item("small", "tiny", priority=1)
    result = pack([big, small], budget_tokens=10)
    assert result.entry_for("big").status == "dropped"
    assert result.entry_for("small").status == "kept"
    assert "x" * 50 not in result.text


def test_custom_tokenizer_changes_the_math():
    by_word = lambda text: len(text.split())  # noqa: E731
    items = [item("a", "one two three four"), item("b", "five six")]
    result = pack(items, budget_tokens=4, token_counter=by_word)
    # 'a' costs 4 words and fits exactly; 'b' then has no room.
    assert result.entry_for("a").status == "kept"
    assert result.entry_for("a").tokens == 4
    assert result.entry_for("b").status == "dropped"


def test_zero_budget_keeps_only_pinned():
    items = [item("p", "rule", pinned=True), item("n", "text", priority=9)]
    result = pack(items, budget_tokens=0)
    assert result.entry_for("p").status == "kept"
    assert result.entry_for("n").status == "dropped"


def test_empty_input_and_validation():
    result = pack([], budget_tokens=10)
    assert result.text == "" and result.used_tokens == 0
    with pytest.raises(ValueError, match="duplicate item name"):
        pack([item("x", "a"), item("x", "b")], budget_tokens=10)
    with pytest.raises(ValueError, match="non-negative"):
        pack([], budget_tokens=-1)
    with pytest.raises(ValueError, match="missing 'text'"):
        Item.from_dict({"name": "x"})
    with pytest.raises(ValueError, match="'priority' must be an integer"):
        Item.from_dict({"name": "x", "text": "t", "priority": 1.5})


def test_load_items_roundtrip_and_errors(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(
        '[{"name": "a", "text": "hello", "priority": 3, "pinned": true}]',
        encoding="utf-8",
    )
    (loaded,) = load_items(path)
    assert loaded.name == "a" and loaded.pinned is True and loaded.priority == 3
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_items(path)
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_items(path)


def test_manifest_shape():
    items = [item("a", "hello world", priority=1), item("b", "x" * 100)]
    result = pack(items, budget_tokens=5)
    manifest = result.manifest()
    assert manifest["metric"] == "contextpack"
    assert manifest["budget_tokens"] == 5
    assert manifest["counts"]["kept"] == 1
    assert manifest["counts"]["dropped"] == 1
    assert manifest["used_tokens"] == result.used_tokens
