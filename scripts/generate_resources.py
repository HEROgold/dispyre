#!/usr/bin/env python3
"""Crawl Discord's resource docs and generate `@model` classes and enums from them.

Discord's docs (a Mintlify site) serve each page as raw markdown at `<page>.md`.
This script reads the page list from `llms.txt`, downloads every page under
`/developers/resources/`, and parses two kinds of tables:

- `| Field | Type | Description |` tables under a "... Structure" or "... Object"
  heading become `@model` dataclasses. `field?` means the key may be missing
  (default `None`), `?type` means the value may be null.
- Tables with a value column (`Value`, `Integer`, `ID`, `Code`) next to a name
  column become `IntEnum`, `IntFlag` (values written as `1 << n`) or `StrEnum`.

- Two-column `Enum|Feature|Type | Description` tables become `StrEnum`s whose
  values are the names themselves.

Endpoint parameter tables (JSON/Form/Query params, response bodies) are skipped.
Types defined outside `/resources/` (roles, teams, components, ...) are pulled in
by following the links in type cells one page deep.

Usage:
    uv run scripts/generate_resources.py            # fetch, cache and generate
    uv run scripts/generate_resources.py --offline  # regenerate from the cache only
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from textwrap import dedent

from docgen import (
    CACHE_DIR,
    DOC_URL,
    DOCS_ROOT,
    INDEX_URL,
    LINK,
    REPO_ROOT,
    Field,
    Model,
    Registry,
    Table,
    build_model,
    column,
    constant,
    docstring,
    fetch,
    identifier,
    is_model_table,
    load_page,
    parse_tables,
    pascal,
    plain,
    render_model,
    strip_suffix,
)

OUTPUT_DIR = REPO_ROOT / "src" / "dispyre" / "discord" / "resources"
PACKAGE = "dispyre.discord.resources"

VALUE_COLUMNS = {"value", "integer", "id", "code"}
NAME_ONLY_COLUMNS = {"enum", "feature", "type"}
SHIFT = re.compile(r"\b1\s*<<\s*(\d+)\b")


@dataclass
class Rule:
    """One computed constant, such as `all_channels(guild_id) = guild_id - 1`."""

    name: str
    param: str
    op: str
    offset: int
    doc: str


@dataclass
class Computed:
    """A table of constants derived from a parameter, rendered as static methods."""

    name: str
    table: Table
    rules: list[Rule] = field(default_factory=list)


@dataclass
class Member:
    """One member of a generated enum."""

    name: str
    value: str
    doc: str


@dataclass
class Enum:
    """An enum generated from a value/name table."""

    name: str
    base: str
    table: Table
    members: list[Member] = field(default_factory=list)


Item = Model | Enum | Computed


def load_pages(*, offline: bool, only: list[str] | None, depth: int) -> dict[str, str]:
    """Return `{docs path: markdown}` for the resource pages plus `depth` rounds of linked pages."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if offline:
        paths = [p.stem.replace("__", "/") for p in sorted(CACHE_DIR.glob("resources__*.md"))]
    else:
        found = DOC_URL.findall(fetch(INDEX_URL))
        paths = [path for path in dict.fromkeys(found) if path.startswith("resources/")]
    if only:
        paths = [path for path in paths if path.removeprefix("resources/") in only]
    pages = {path: text for path in paths if (text := load_page(path, offline=offline))}
    print(f"depth 0: {len(pages)} resource pages")

    frontier = dict(pages)
    for level in range(1, depth + 1):
        new = sorted(linked_pages(frontier) - pages.keys())
        frontier = {path: text for path in new if (text := load_page(path, offline=offline))}
        print(f"depth {level}: +{len(frontier)} pages {sorted(frontier)}")
        if not frontier:
            break
        pages.update(frontier)
    return pages


def linked_pages(pages: dict[str, str]) -> set[str]:
    """Docs paths linked from the type cells of the pages' model tables."""
    linked: set[str] = set()
    for path, markdown in pages.items():
        for table in parse_tables(path, markdown):
            if is_model_table(table):
                for row in table.rows:
                    if len(row) > 1:
                        urls = " ".join(url for _, url in LINK.findall(row[1]))
                        linked.update(DOC_URL.findall(urls))
    return linked


def enum_columns(table: Table) -> tuple[int, int] | None:
    """Return `(value column, name column)` for an enum table, else `None`."""
    header = [cell.lower() for cell in table.header]
    if not header or header[0] == "field":
        return None
    if header in ([name, "description"] for name in NAME_ONLY_COLUMNS):
        return (0, 0)
    value = next((i for i, cell in enumerate(header) if cell in VALUE_COLUMNS), None)
    if value is None:
        return None
    name = next((i for i, cell in enumerate(header) if i != value and cell != "description"), None)
    return None if name is None else (value, name)


def enum_value(cell: str) -> tuple[str, str] | None:
    """Return `(kind, python literal)` for a value cell, or `None` if it isn't one."""
    text = plain(cell).rstrip("*").strip().strip("\"'")
    if re.fullmatch(r"-?\d+", text):
        return "int", text
    if match := SHIFT.search(text):  # "1 << 3", or "0x08 (1 << 3)" on the permissions page
        return "flag", f"1 << {match.group(1)}"
    if text and not re.search(r"\s", text):
        return "str", repr(text)
    return None


# --- building ---------------------------------------------------------------


def build_enum(table: Table, columns: tuple[int, int], registry: Registry) -> Enum | None:
    value_col, name_col = columns
    desc_col = column(table, "description")
    rows = [row for row in table.rows if len(row) > value_col and plain(row[value_col])]
    parsed = [enum_value(row[value_col]) for row in rows]
    values = [value for value in parsed if value is not None]
    if not values or len(values) != len(rows):
        return None
    kinds = {kind for kind, _ in values}
    if kinds == {"str"}:
        base = "StrEnum"
    elif kinds <= {"int", "flag"}:
        base = "IntFlag" if "flag" in kinds else "IntEnum"
    else:
        return None
    name = registry.claim(pascal(table.heading), table)
    enum = Enum(name, base, table)
    seen: set[str] = set()
    for row, (_, literal) in zip(rows, values, strict=True):
        name_cell = row[name_col].strip("'\"") if len(row) > name_col else ""
        member = constant(name_cell) if name_cell else ""
        if not member.strip("_") or member in seen:
            member = constant(f"{member}_{literal}")
        seen.add(member)
        doc = plain(row[desc_col]) if desc_col is not None and len(row) > desc_col else ""
        enum.members.append(Member(member, literal, doc))
    return enum


# Tables whose values are expressions: accept only `name` or `name +/- digits`, so no
# text from the docs ever ends up in generated code unchecked.
EXPRESSION = re.compile(r"^([a-z][a-z_]*)(?:\s*([-+])\s*(\d+))?$")


def build_computed(table: Table, columns: tuple[int, int], registry: Registry) -> Computed | None:
    """Turn a snowflake-typed table of `param +/- n` values into static methods."""
    value_col, name_col = columns
    type_col, desc_col = column(table, "type"), column(table, "description")
    computed = Computed("", table)
    for row in table.rows:
        match = EXPRESSION.match(plain(row[value_col])) if len(row) > value_col else None
        is_snowflake = type_col is not None and plain(row[type_col]).lower() == "snowflake"
        if match is None or not is_snowflake:
            return None
        param, op, offset = match.group(1), match.group(2) or "", int(match.group(3) or 0)
        doc = plain(row[desc_col]) if desc_col is not None else ""
        name = identifier(plain(row[name_col]).lower())
        computed.rules.append(Rule(name.strip("_") or name, param, op, offset, doc))
    computed.name = registry.claim(pascal(table.heading), table)
    return computed


# --- rendering --------------------------------------------------------------


def module_name(page: str) -> str:
    """`resources/user` -> `user`, `topics/permissions` -> `topics_permissions`."""
    return page.removeprefix("resources/").replace("/", "_").replace("-", "_")


def render_module(page: str, items: list[Item], owner: dict[str, str]) -> str:
    """Render one docs page as a Python module."""
    local = {item.name for item in items}
    used: set[str] = set()
    bodies: list[str] = []
    for item in items:
        if isinstance(item, Enum):
            bodies.append(render_enum(item))
        elif isinstance(item, Computed):
            bodies.append(render_computed(item))
            used.add("Snowflake")
        else:
            bodies.append(render_model(item))
            for f in item.fields:
                used.update(re.findall(r"[A-Za-z_]\w*", f.annotation))
    header = dedent(f'''\
        """Models for Discord's {page.rpartition("/")[2].replace("-", " ")} docs page.

        Generated by `scripts/generate_resources.py` from
        {DOCS_ROOT}/developers/{page}. Do not edit by hand.
        """

        from __future__ import annotations

        ''')
    body = "\n\n\n".join(bodies)
    cross = render_cross_imports(page, used - local, owner)
    return f"{header}{render_imports(items, used)}\n\n{body}\n{cross}"


def render_imports(items: list[Item], used: set[str]) -> str:
    """Top-of-module imports: enum bases, `Any`, `model` and the scalar aliases."""
    lines: list[str] = []
    if enum_bases := sorted({item.base for item in items if isinstance(item, Enum)}):
        lines.append(f"from enum import {', '.join(enum_bases)}\n")
    if "Any" in used:
        lines.append("from typing import Any\n")
    if any(isinstance(item, Model) for item in items):
        lines.append("\nfrom dispyre.base import model\n")
    if aliases := sorted(used & {"ISO8601Timestamp", "Snowflake"}):
        lines.append(f"from {PACKAGE}._types import {', '.join(aliases)}\n")
    return "".join(lines)


def render_cross_imports(page: str, names: set[str], owner: dict[str, str]) -> str:
    """Bottom-of-module imports of classes from other pages (E402 is ignored in ruff.toml)."""
    imports: dict[str, list[str]] = {}
    for name in sorted(names):
        if name in owner and owner[name] != page:
            imports.setdefault(owner[name], []).append(name)
    if not imports:
        return ""
    text = "\n\n# Imported last so circular references between modules resolve at runtime.\n"
    for module, module_names in sorted(imports.items()):
        text += f"from {PACKAGE}.{module_name(module)} import {', '.join(module_names)}\n"
    return text


def render_enum(item: Enum) -> str:
    source = f"{DOCS_ROOT}/developers/{item.table.page}#{item.table.anchors[-1]}"
    lines = [
        f"class {item.name}({item.base}):",
        docstring(f"{plain(item.table.heading)}.", extra=source),
    ]
    for member in item.members:
        lines.append(f"\n    {member.name} = {member.value}")
        if member.doc:
            lines.append(docstring(member.doc))
    return "\n".join(lines)


def render_computed(item: Computed) -> str:
    source = f"{DOCS_ROOT}/developers/{item.table.page}#{item.table.anchors[-1]}"
    lines = [f"class {item.name}:", docstring(f"{plain(item.table.heading)}.", extra=source)]
    for rule in item.rules:
        expression = rule.param
        if rule.op:  # snowflakes are strings: do the arithmetic on ints, then convert back
            expression = f"Snowflake(str(int({rule.param}) {rule.op} {rule.offset}))"
        lines.append("\n    @staticmethod")
        lines.append(f"    def {rule.name}({rule.param}: Snowflake) -> Snowflake:")
        if rule.doc:
            lines.append(docstring(rule.doc, "        "))
        lines.append(f"        return {expression}")
    return "\n".join(lines)


TYPES_MODULE = dedent('''\
    """Scalar aliases shared by the generated resource models.

    Generated by `scripts/generate_resources.py`. Do not edit by hand.
    """

    from datetime import UTC, datetime
    from typing import NewType, TypeAlias

    DISCORD_EPOCH_MS = 1_420_070_400_000
    """2015-01-01T00:00:00Z, the zero point of snowflake timestamps."""

    Snowflake = NewType("Snowflake", str)
    """A Discord id, kept as the string the API sends. Distinct from `str` for type checkers."""

    ISO8601Timestamp: TypeAlias = str
    """An ISO 8601 timestamp string as sent by the API."""


    def snowflake_time(snowflake: Snowflake) -> datetime:
        """When the object behind `snowflake` was created."""
        return datetime.fromtimestamp(((int(snowflake) >> 22) + DISCORD_EPOCH_MS) / 1000, UTC)
    ''')


def render_init(owner: dict[str, str], pages: list[str]) -> str:
    lines = [
        dedent('''\
            """Models representing Discord resources.

            Generated by `scripts/generate_resources.py` from
            https://docs.discord.com/developers/resources. Do not edit by hand.
            """

            '''),
    ]
    by_page: dict[str, list[str]] = {}
    for name, page in owner.items():
        by_page.setdefault(page, []).append(name)
    for page in pages:
        names = sorted(by_page.get(page, []))
        if names:
            joined = ", ".join(names)
            lines.append(f"from {PACKAGE}.{module_name(page)} import ({joined},)\n")
    lines.append("\n__all__ = [\n")
    lines.extend(f'    "{name}",\n' for name in sorted(owner))
    lines.append("]\n")
    return "".join(lines)


# --- main -------------------------------------------------------------------


def generate(pages: dict[str, str]) -> Registry:
    registry = Registry()
    per_page: dict[str, list[Item]] = {page: [] for page in pages}
    models: list[Model] = []
    skipped: list[str] = []

    # Pass 1: name every class and register its anchors, so links resolve in pass 2.
    for page, markdown in pages.items():
        for table in parse_tables(page, markdown):
            if is_model_table(table):
                name = registry.claim(pascal(strip_suffix(table.heading)), table)
                registry.register(name, table)
                registry.models.add(name)
                item = Model(name, table)
                models.append(item)
                per_page[page].append(item)
            elif columns := enum_columns(table):
                item = build_enum(table, columns, registry) or build_computed(
                    table, columns, registry
                )
                if item is None:
                    skipped.append(f"{page}: {plain(table.heading)} (unparseable values)")
                    continue
                registry.register(item.name, table)
                per_page[page].append(item)

    # Pass 2: resolve field types now that every anchor is known.
    for item in models:
        build_model(item, registry)
    add_partials(per_page, registry)

    write_output(per_page)
    report(per_page, skipped, registry)
    return registry


def add_partials(per_page: dict[str, list[Item]], registry: Registry) -> None:
    """Insert a `PartialX` right after each model X that a "partial [x]" type points at."""
    for page, items in per_page.items():
        result: list[Item] = []
        for item in items:
            result.append(item)
            if isinstance(item, Model) and item.name in registry.partials:
                name = registry.claim(f"Partial{item.name}", item.table)
                partial = Model(name, item.table, partial_of=item.name)
                for f in item.fields:
                    annotation = f.annotation
                    if not annotation.endswith(" | None"):
                        annotation = f"{annotation} | None"
                    partial.fields.append(Field(f.name, annotation, optional=True, doc=f.doc))
                result.append(partial)
        per_page[page] = result


GENERATED_MARKER = "Generated by `scripts/generate_resources.py`"


def write_output(per_page: dict[str, list[Item]]) -> None:
    """Write one module per page plus `_types.py` and `__init__.py`, then ruff them."""
    owner = {item.name: page for page, items in per_page.items() for item in items}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = {OUTPUT_DIR / "_types.py", OUTPUT_DIR / "__init__.py"}
    (OUTPUT_DIR / "_types.py").write_text(TYPES_MODULE, "utf-8")
    for page, items in per_page.items():
        if items:
            path = OUTPUT_DIR / f"{module_name(page)}.py"
            path.write_text(render_module(page, items, owner), "utf-8")
            written.add(path)
    (OUTPUT_DIR / "__init__.py").write_text(render_init(owner, list(per_page)), "utf-8")
    # Drop modules an earlier run generated but this one didn't (say, after lowering --depth).
    for path in OUTPUT_DIR.glob("*.py"):
        if path not in written and GENERATED_MARKER in path.read_text("utf-8")[:500]:
            print(f"removing stale {path.name}")
            path.unlink()
    ruff = ["uv", "run", "ruff"]
    subprocess.run([*ruff, "check", "--fix", "--quiet", str(OUTPUT_DIR)], check=False)
    subprocess.run([*ruff, "format", "--quiet", str(OUTPUT_DIR)], check=True)


def report(per_page: dict[str, list[Item]], skipped: list[str], registry: Registry) -> None:
    items = [item for page_items in per_page.values() for item in page_items]
    counts = {
        kind.__name__: sum(isinstance(item, kind) for item in items)
        for kind in (Model, Enum, Computed)
    }
    partials = sum(isinstance(item, Model) and bool(item.partial_of) for item in items)
    summary = ", ".join(f"{n} {kind}" for kind, n in counts.items() if n)
    print(f"\n{len(per_page)} pages: {summary} ({partials} partials) -> {OUTPUT_DIR}")
    for line in skipped:
        print(f"skipped {line}")
    if registry.unresolved:
        total = sum(registry.unresolved.values())
        print(f"\n{total} unresolved types (emitted as Any / dict[str, Any]):")
        for text, count in sorted(registry.unresolved.items(), key=lambda kv: -kv[1]):
            print(f"  {count:3}x  {text}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="only use cached pages")
    parser.add_argument("--pages", nargs="*", help="page slugs to include, e.g. user channel")
    parser.add_argument(
        "--depth", type=int, default=2, help="rounds of linked pages to follow (default 2)"
    )
    args = parser.parse_args()
    generate(load_pages(offline=args.offline, only=args.pages, depth=args.depth))


if __name__ == "__main__":
    main()
