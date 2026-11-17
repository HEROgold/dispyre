"""Smoke test: the package must import cleanly with no side-effect errors."""

import importlib


def test_import() -> None:
    importlib.import_module("dispyre")
