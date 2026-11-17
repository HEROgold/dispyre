---
name: release-process
description: How releases happen in this project — label-driven, automatic on merge.
---

# Release process

Releases are **label-driven** and fully automatic once a PR merges. There
is no manual version bump, tag, or changelog step.

1. On the PR you want released, apply exactly one of:
   - `bump:major`
   - `bump:minor`
   - `bump:patch`
2. Merge the PR.
3. CI then automatically:
   - Bumps the version according to the label.
   - Creates the git tag.
   - Creates the GitHub release.
   - Builds and pushes the Docker image to GHCR (GitHub Container
     Registry).
If a PR doesn't carry one of the `bump:*` labels, merging it does **not**
trigger a release — use that for internal chores, docs-only changes, etc.
that shouldn't ship a new version on their own.

Don't hand-edit the version in `pyproject.toml` — it's derived from the
tag history by the release automation.
