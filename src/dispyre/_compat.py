"""Compatibility helpers for dispyre."""

from importlib.util import find_spec


def require(module: str, extra: str) -> None:
    if find_spec(module) is None:
        msg = f"{module} is not installed; install dispyre[{extra}]"
        raise ImportError(msg)


def optional(module: str) -> bool:
    return find_spec(module) is not None


HAS_PYDANTIC = optional("pydantic")
