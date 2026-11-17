#!/usr/bin/env python3
"""Run everything: lint, typecheck, then test — stopping at the first failure.

This is the single local sanity check to run before pushing; it's exactly
what `just check` wraps. Each step shells out to the corresponding
scripts/*.py so there is only one place that defines what "lint" or
"typecheck" or "test" actually means.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

STEPS = [
    ("lint", SCRIPTS_DIR / "lint.py"),
    ("typecheck", SCRIPTS_DIR / "typecheck.py"),
    ("test", SCRIPTS_DIR / "test.py"),
]


def main() -> int:
    for name, script in STEPS:
        print(f"==> {name}")
        result = subprocess.run([sys.executable, str(script)], check=False)
        if result.returncode != 0:
            print(f"==> {name} failed, stopping.", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
