#!/usr/bin/env python3
"""Build or serve the project's documentation site with Zensical.

Invoke via `uv run scripts/docs.py` (or `just docs`) for a local live-reload
preview, or `uv run scripts/docs.py --build` for a static build to ./site.

NOTE: Zensical is a new tool (announced November 2025) positioned as a
backward-compatible successor to MkDocs, reusing MkDocs-style config and CLI
conventions (`zensical serve` / `zensical build`). That compatibility is
based on Zensical's own announced positioning, not something verified
against a hands-on run here — double-check `uvx zensical --help` (or current
Zensical docs) against this script if `zensical serve`/`zensical build`
don't behave as expected.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build a static site to ./site instead of serving it locally.",
    )
    args = parser.parse_args()

    command = ["uvx", "zensical", "build" if args.build else "serve"]
    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
