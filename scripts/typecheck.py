#!/usr/bin/env python3
"""Run the configured type checker(s) over the project.

Invoke via `uv run scripts/typecheck.py` (or `just typecheck`). Runs one
subprocess per type checker selected at generation time, stopping at the
first failure.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(["uv", "run", "ty", "check"], check=False)
    if result.returncode != 0:
        return result.returncode

    result = subprocess.run(["uv", "run", "pyrefly", "check"], check=False)
    if result.returncode != 0:
        return result.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
