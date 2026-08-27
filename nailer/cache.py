"""Tiny per-day JSON file cache so repeated `nailer` runs on the same day
don't hammer the ESPN/Yahoo endpoints. Not a general-purpose cache: keys
are just (league, endpoint, params) and values must be JSON-serializable.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, cache_dir: Path, ttl_hours: int = 24, enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_hours * 3600
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, league: str, endpoint: str, params: dict[str, Any]) -> Path:
        raw = json.dumps({"league": league, "endpoint": endpoint, "params": params}, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return self.cache_dir / f"{league}_{endpoint}_{digest}.json"

    def get_or_fetch(
        self,
        league: str,
        endpoint: str,
        params: dict[str, Any],
        fetch_fn: Callable[[], Any],
    ) -> Any:
        if not self.enabled:
            return fetch_fn()

        path = self._key_path(league, endpoint, params)
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < self.ttl_seconds:
                try:
                    with path.open() as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass  # fall through and refetch

        result = fetch_fn()
        try:
            with path.open("w") as f:
                json.dump(result, f)
        except (TypeError, OSError):
            pass  # non-serializable or unwritable; just skip caching this call
        return result
