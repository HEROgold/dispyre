# Task runner for Dispyre.
#
# Every recipe here is a thin, one-line wrapper around a script in scripts/.
# The scripts are the single source of truth for the actual logic — that
# means `uv run scripts/xxx.py` alone (no `just` installed) is always a
# complete, working fallback, never a partial one. Don't add logic here that
# isn't also in the script it calls.

default:
    @just --list

install:
    uv sync
    uv run prek install
    uv run prek install --hook-type pre-push

lint:
    uv run scripts/lint.py

format:
    uv run scripts/format.py

typecheck:
    uv run scripts/typecheck.py

test:
    uv run scripts/test.py

test-cov:
    uv run scripts/test.py --cov

check:
    uv run scripts/check.py

docs:
    uv run scripts/docs.py
