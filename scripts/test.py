#!/usr/bin/env python3
"""Run the test suite with pytest.

Invoke via `uv run scripts/test.py` (or `just test`).
Pass `--cov` to additionally collect and report coverage for
`dispyre`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cov",
        action="store_true",
        help="Collect coverage for dispyre and report missing lines.",
    )
    args = parser.parse_args()

    # pytest.toml (and coverage.toml) are standalone files, not `[tool.*]`
    # tables in pyproject.toml — neither pytest nor coverage.py auto-discover
    # a bare "pytest.toml"/"coverage.toml", so they must be pointed at
    # explicitly.
    command = ["uv", "run", "pytest", "-c", "pytest.toml"]
    if args.cov:
        command += [
            "--cov=dispyre",
            "--cov-report=term-missing",
            "--cov-config=coverage.toml",
        ]

    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
