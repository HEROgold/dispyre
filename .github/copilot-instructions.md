# Instructions for AI coding agents

This repository was generated from HEROgold's `pytemplate` Copier template.
A few conventions are load-bearing — follow them rather than reaching for
whatever's idiomatic elsewhere.

## Package management

- Always use `uv` (`uv add`, `uv sync`, `uv run ...`). Never invoke `pip`
  directly, and never edit `uv.lock` by hand.
- Dependency groups live in `pyproject.toml` under `[dependency-groups]`.

## Tool configuration lives in standalone files

Ruff, pytest, and coverage are configured in their own top-level files
(`ruff.toml`, `pytest.toml`, `coverage.toml`) rather than `[tool.*]` tables
inside `pyproject.toml`. Keep it that way — `pyproject.toml` stays focused
on packaging metadata only. If you add a new tool, prefer its own config
file over a `pyproject.toml` table when the tool supports one.

## `justfile` wraps `scripts/`, never contains logic itself

Every `just` recipe should be a thin call into a script under `scripts/`
(e.g. `just test` → `uv run scripts/test.py`). Do not put multi-line shell
logic, conditionals, or anything beyond a single delegating command
directly in the `justfile`. If a recipe needs new behavior, edit or add a
script, not the recipe.

## Hooks run via `prek`, invoking tools through `uvx`

Git hooks are managed by [`prek`](https://github.com/j178/prek), a faster,
drop-in-compatible reimplementation of pre-commit — it reads the same
`.pre-commit-config.yaml`, and `uv run prek install`/`prek run` behave like
their pre-commit equivalents. Local hooks invoke tools through `uvx` (or a
tool's native pre-commit-compatible hook where one is published) rather than
assuming the tool is installed in the environment already. Keep new hooks
consistent with that.

## Project layout is `project_kind`-specific

This is a **library** project: no `__main__.py`, no entry point. It exists
to be imported. Keep the public API surfaced through `src/dispyre/__init__.py`.

## When in doubt

Check `.github/skills/` for task-specific guidance (running tests, lint and
typecheck, the release process) before improvising.
