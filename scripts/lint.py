#!/usr/bin/env python3
"""Run ruff's linter over the project.

Invoke via `uv run scripts/lint.py` (or `just lint`).
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    # Only the linter runs here; `ruff format --check` is intentionally left
    # to scripts/check.py's own lint step (kept identical to this one) rather
    # than duplicated — formatting itself lives in scripts/format.py, which
    # rewrites files instead of just checking them.
    result = subprocess.run(["uv", "run", "ruff", "check", "."], check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
