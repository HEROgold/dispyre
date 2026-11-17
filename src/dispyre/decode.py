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
- For a union of models, a member with `Literal` fields (a discriminator such as a
    component's `type`) wins when the data holds one of its values. Otherwise the first model
    whose required fields are all present wins.
- A field declared with `field(metadata={"key": "_errors"})` reads and writes that JSON key.

`encode` goes the other way: it turns models into JSON-ready dicts, leaving out optional
fields that are `None`.
"""

from __future__ import annotations

import dataclasses
import keyword
import types
import typing
from collections.abc import Mapping
from enum import Enum, Flag
from functools import cache
from typing import TYPE_CHECKING, Any, Literal, TypeVar, get_args, get_origin, get_type_hints

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


def encode(value: Any) -> Any:  # noqa: ANN401 - mirrors `decode`: any model, list or scalar
    """Turn a model (or a list or dict of them) into JSON-ready data.

    Optional fields left at `None` are dropped; a required field that is `None` stays, because
    the API reads it as an explicit null. Enums become their values.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        keys = _fields(type(value))
        result: dict[str, Any] = {}
        for f in dataclasses.fields(value):
            item = getattr(value, f.name)
            if item is None and f.default is None:
                continue
            result[keys[f.name][0]] = encode(item)
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [encode(item) for item in value]
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
        return _decode_model_union(options, value)
    if isinstance(value, list):
        lists = [option for option in options if get_origin(option) is list]
        return decode(lists[0], value) if lists else value
    for option in options:
        if isinstance(option, type) and issubclass(option, Enum) and value in _enum_values(option):
            return option(value)
    return value


def _decode_model_union(options: tuple[Any, ...], value: Mapping[str, Any]) -> Any:  # noqa: ANN401
    """Pick the model `value` fits: by discriminator, else by its required keys."""
    models = [option for option in options if dataclasses.is_dataclass(option)]
    tagged = [option for option in models if _tag_matches(option, value)]
    for group in (tagged, models):
        for option in group:
            if _required_keys(option) <= value.keys():
                return from_dict(option, value)
    chosen = tagged or models
    return from_dict(chosen[0], value) if chosen else value


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
        result[f.name] = (f.metadata.get("key", key), hints[f.name])
    return result


@cache
def _tags(cls: type[DataclassInstance]) -> dict[str, frozenset[Any]]:
    """`{json key: allowed values}` for `Literal[...]` fields, which tell union members apart."""
    return {
        key: frozenset(get_args(hint))
        for key, hint in _fields(cls).values()
        if get_origin(hint) is Literal
    }


def _tag_matches(cls: type[DataclassInstance], value: Mapping[str, Any]) -> bool:
    tags = _tags(cls)
    return bool(tags) and all(
        key in value and value[key] in allowed for key, allowed in tags.items()
    )


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
