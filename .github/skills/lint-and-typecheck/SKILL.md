---
name: lint-and-typecheck
description: How to run lint, format, and typecheck in this project.
---

# Lint, format, and typecheck

```bash
just lint       # ruff check
just format     # ruff format
just typecheck  # configured type checker(s), see below
```

Each recipe wraps a script under `scripts/` — don't call `ruff`/the type
checkers directly unless debugging, since the scripts apply the project's
configured options (`ruff.toml`, etc.).

## Type checkers configured for local/day-to-day feedback

- ty
- pyrefly

Note: regardless of what's configured above, this project's CI also runs a
public-API compatibility gate across **all five** type checkers (mypy,
pyright, pyrefly, ty, zuban) — that gate is about downstream-user coverage
across the ecosystem, not day-to-day dev ergonomics, so it always runs in
full even if you only have a subset configured locally.
