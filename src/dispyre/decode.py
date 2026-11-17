"""Build `@model` dataclasses from JSON payloads.

`from_dict` walks `typing.get_type_hints` of the target class and builds nested
models, lists, dicts and enums. It works with both `model` backends: plain
dataclasses get real nested objects, and pydantic dataclasses receive values that
are already the right type.

Rules:
- Keys the class doesn't declare are ignored, so new API fields don't break decoding.
- A field named after a Python keyword (`global_`) reads the key without the `_`.
- `NewType`s decode as their base type, and an `int` field accepts a numeric string,
    because the API sends snowflakes as strings.
- An enum field keeps the raw value when Discord sends a value the enum doesn't know.
- For a union of models, the first model whose required fields are all present wins.
"""

from __future__ import annotations

import dataclasses
import keyword
import types
import typing
from collections.abc import Mapping
from enum import Enum, Flag
from functools import cache
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_origin, get_type_hints

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

T = TypeVar("T")


def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
    """Build `cls` from a JSON object, decoding nested values by their annotations."""
    kwargs = {
        name: decode(hint, data[key]) for name, (key, hint) in _fields(cls).items() if key in data
    }
    return cls(**kwargs)


def decode(hint: Any, value: Any) -> Any:  # noqa: ANN401 - dispatches on any type hint
    """Decode one JSON value into the type `hint` describes."""
    hint = _unwrap_newtype(hint)
    if value is None or hint is Any:
        return value
    origin = get_origin(hint)
    if origin in (types.UnionType, typing.Union):
        return _decode_union(get_args(hint), value)
    if origin is list and isinstance(value, list):
        (item,) = get_args(hint) or (Any,)
        return [decode(item, element) for element in value]
    if origin is dict and isinstance(value, Mapping):
        key_hint, value_hint = get_args(hint) or (Any, Any)
        return {decode(key_hint, k): decode(value_hint, v) for k, v in value.items()}
    if isinstance(hint, type):
        return _decode_class(hint, value)
    return value


def _decode_class(hint: type, value: Any) -> Any:  # noqa: ANN401
    if dataclasses.is_dataclass(hint) and isinstance(value, Mapping):
        return from_dict(hint, value)
    if issubclass(hint, Flag) and isinstance(value, int):
        return hint(value)  # IntFlag keeps unknown bits
    if issubclass(hint, Enum):
        return hint(value) if value in _enum_values(hint) else value
    if hint is int and isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _decode_union(options: tuple[Any, ...], value: Any) -> Any:  # noqa: ANN401
    """Pick the union member that fits `value`, then decode with it."""
    options = tuple(_unwrap_newtype(option) for option in options if option is not type(None))
    if len(options) == 1:
        return decode(options[0], value)
    if isinstance(value, Mapping):
        models = [option for option in options if dataclasses.is_dataclass(option)]
        for option in models:
            if _required_keys(option) <= value.keys():
                return from_dict(option, value)
        return from_dict(models[0], value) if models else value
    if isinstance(value, list):
        lists = [option for option in options if get_origin(option) is list]
        return decode(lists[0], value) if lists else value
    for option in options:
        if isinstance(option, type) and issubclass(option, Enum) and value in _enum_values(option):
            return option(value)
    return value


def _unwrap_newtype(hint: Any) -> Any:  # noqa: ANN401
    while hasattr(hint, "__supertype__"):
        hint = hint.__supertype__
    return hint


@cache
def _fields(cls: type[DataclassInstance]) -> dict[str, tuple[str, Any]]:
    """`{attribute: (json key, resolved type hint)}` for a dataclass."""
    hints = get_type_hints(cls)
    result: dict[str, tuple[str, Any]] = {}
    for f in dataclasses.fields(cls):
        key = f.name[:-1] if f.name.endswith("_") and keyword.iskeyword(f.name[:-1]) else f.name
        result[f.name] = (key, hints[f.name])
    return result


@cache
def _required_keys(cls: type[DataclassInstance]) -> frozenset[str]:
    keys = _fields(cls)
    return frozenset(
        keys[f.name][0]
        for f in dataclasses.fields(cls)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    )


@cache
def _enum_values(cls: type[Enum]) -> frozenset[Any]:
    return frozenset(member.value for member in cls)
