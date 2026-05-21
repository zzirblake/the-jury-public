"""Tiny local environment loader.

The public package does not include secrets. This helper walks up from cwd
looking for a local environment file, parses simple KEY=VALUE lines, and
exports any key whose name contains "llm", "api", and "key" (case-insensitive)
as LLM_API_KEY in os.environ.

Skips if LLM_API_KEY is already set.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_anthropic_key(start: Path | None = None) -> bool:
    """Return True if an API key was loaded (or was already present)."""
    if os.environ.get("LLM_API_KEY"):
        return True
    here = Path(start) if start else Path(__file__).resolve()
    for parent in [here, *here.parents]:
        env_path = parent / ".env"
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            kl = key.lower()
            if "llm" in kl and "api" in kl and "key" in kl:
                os.environ["LLM_API_KEY"] = value
                return True
    return False
