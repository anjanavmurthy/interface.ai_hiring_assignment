"""Load API keys from a .env file without extra packages."""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(*candidates: Path) -> None:
    """Read KEY=value lines from the first existing files among `candidates` into the environment.

    Variables that are already set win, so an exported ANTHROPIC_API_KEY is never overridden.
    Lines starting with '#' and lines without '=' are ignored; surrounding quotes are stripped.
    """
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
