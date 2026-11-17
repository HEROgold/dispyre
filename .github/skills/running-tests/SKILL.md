---
name: running-tests
description: How to run this project's test suite, with or without coverage.
---

# Running tests

Run the full test suite with:

```bash
just test
```

which wraps:

```bash
uv run scripts/test.py
```

## With coverage

```bash
just test-cov
```

Coverage is enforced at a **95% threshold** (configured in `coverage.toml`)
— CI fails the build if coverage drops below it. Run this locally before
opening a PR if you've touched code paths that might be under-tested.

Don't invoke `pytest` directly unless you're debugging a single test
interactively — `just test` picks up the project's configured options
(`pytest.toml`) that a bare `pytest` invocation won't.
