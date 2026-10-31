"""contextpack: assemble LLM context under a hard token budget."""

from .demo import run_demo
from .pack import (
    Item,
    ManifestEntry,
    PackResult,
    estimate_tokens,
    load_items,
    pack,
)

__version__ = "0.1.0"

__all__ = [
    "Item",
    "ManifestEntry",
    "PackResult",
    "estimate_tokens",
    "load_items",
    "pack",
    "run_demo",
    "__version__",
]
