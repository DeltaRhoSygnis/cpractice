"""Cache for validated generation results.

Caching is the primary defence against quota exhaustion: a problem is
generated once and reused across attempts. Keys are derived from the request
parameters so identical requests never re-consume quota.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class GenerationCache:
    """A simple content-addressed JSON cache on disk."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(parameters: dict[str, Any]) -> str:
        """Derive a stable cache key from request parameters."""
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a cached payload, or None on miss or corruption."""
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt cache entry is a miss, never a hard failure.
            return None

    def put(self, key: str, payload: dict[str, Any]) -> Path:
        """Store a payload and return the path written."""
        path = self.path_for(key)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def has(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def clear(self) -> int:
        """Delete every entry. Returns the number removed."""
        removed = 0
        for entry in self.root.glob("*.json"):
            entry.unlink(missing_ok=True)
            removed += 1
        return removed
