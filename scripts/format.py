#!/usr/bin/env python3
"""Format the project with ruff, fixing whatever lint issues are auto-fixable.

Invoke via `uv run scripts/format.py` (or `just format`).
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    fix = subprocess.run(["uv", "run", "ruff", "check", "--fix", "."], check=False)
    fmt = subprocess.run(["uv", "run", "ruff", "format", "."], check=False)
    return fix.returncode or fmt.returncode


if __name__ == "__main__":
    sys.exit(main())
