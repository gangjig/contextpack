"""The demo: one context assembly under a budget too small for
everything. A pinned system prompt and the current task are untouchable,
a huge tool result is truncatable, and yesterday's conversation is
the first thing to go. The manifest shows every decision.
"""

from __future__ import annotations

from .pack import Item, PackResult, pack

DEMO_BUDGET = 260


def _tool_result_text() -> str:
    lines = ["# auth.py (tool result, 40 lines)"]
    for i in range(1, 40):
        lines.append(f"line {i:02d}: value_{i} = compute_step_{i}(request)")
    return "\n".join(lines)


def demo_items() -> list[Item]:
    return [
        Item(
            name="system",
            text=(
                "You are a careful coding agent. Always run the tests "
                "before you finish, and never edit a file you have not read."
            ),
            priority=100,
            pinned=True,
        ),
        Item(
            name="task",
            text=(
                "Fix the auth bug in auth.py: users with expired tokens "
                "are still being let in. Run the test suite when done."
            ),
            priority=90,
        ),
        Item(
            name="retrieved_doc",
            text=(
                "Style guide excerpt: token checks must compare expiry "
                "against the server clock, never the client clock. All "
                "auth failures return the same generic error message."
            ),
            priority=60,
        ),
        Item(
            name="recent_history",
            text=(
                "User: the login page also flashes an error on success. "
                "Agent: noted, likely the same token check. I will look "
                "at auth.py first."
            ),
            priority=50,
        ),
        Item(
            name="tool_result",
            text=_tool_result_text(),
            priority=40,
            truncatable=True,
        ),
        Item(
            name="old_history",
            text=(
                "Yesterday: user asked about password reset emails; "
                "agent explained the mail queue; user asked about "
                "session cookies; agent summarized the cookie policy; "
                "user said thanks and closed the topic."
            ),
            priority=10,
        ),
    ]


def run_demo() -> PackResult:
    return pack(demo_items(), DEMO_BUDGET)


def render_manifest_markdown(result: PackResult) -> str:
    lines = [
        "| Item | Status | Tokens | Kept |",
        "|---|---|---:|---:|",
    ]
    for entry in result.entries:
        status = (
            entry.status
            if entry.status == "kept"
            else f"**{entry.status}**"
        )
        lines.append(
            f"| {entry.name} | {status} | {entry.tokens} | {entry.kept_tokens} |"
        )
    lines.append(
        f"\nBudget: {result.budget_tokens} tokens; used: "
        f"{result.used_tokens}."
    )
    return "\n".join(lines)
