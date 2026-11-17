"""Shared parsing, type resolution and rendering for the Discord docs generators.

Discord's docs (a Mintlify site) serve each page as raw markdown at `<page>.md`. The
generators in this folder (`generate_resources.py`, `generate_gateway_events.py`) fetch
those pages, parse the markdown tables into `Table`s, and turn `Field | Type |
Description` tables into `Model`s whose field types resolve through a `Registry`.
"""

from __future__ import annotations

import json
import keyword
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import wrap
from typing import Any

DOCS_ROOT = "https://docs.discord.com"
INDEX_URL = f"{DOCS_ROOT}/llms.txt"
DOC_URL = re.compile(rf"{re.escape(DOCS_ROOT)}/developers/([a-z0-9/-]+)\.md")
REPO_ROOT = Path(__file__).resolve().parent.parent


CACHE_DIR = REPO_ROOT / ".cache" / "discord-docs"


LINE_LIMIT = 100  # ruff.toml line-length
USER_AGENT = "dispyre-docgen (+https://github.com/HEROgold/dispyre)"


HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
TABLE_RULE = re.compile(r"^\|\s*:?-")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
SKIPPED_HEADING = re.compile(r"\b(params|parameters|response body)$", re.IGNORECASE)


PRIMITIVES = {
    "snowflake": "Snowflake",
    "string": "str",
    "str": "str",
    "integer": "int",
    "int": "int",
    "number": "float",
    "float": "float",
    "double": "float",
    "boolean": "bool",
    "bool": "bool",
    "iso8601 timestamp": "ISO8601Timestamp",
    "is08601 timestamp": "ISO8601Timestamp",  # typo in the docs
    "object": "dict[str, Any]",
    "dict": "dict[str, Any]",
    "mixed": "Any",
}
PLURALS = {"snowflakes": "snowflake", "strings": "string", "integers": "integer", "ints": "int"}


@dataclass
class Table:
    """One markdown table plus the headings it sits under."""

    page: str
    heading: str
    container: str
    anchors: list[str]
    container_anchors: list[str]
    header: list[str]
    rows: list[list[str]]
    footnotes: dict[int, str] = field(default_factory=dict)
    """Text of the `\\*` lines under the table, keyed by how many asterisks mark them."""


@dataclass
class Field:
    """One field of a generated model."""

    name: str
    annotation: str
    optional: bool
    doc: str


@dataclass
class Model:
    """A class generated from a `Field | Type` table."""

    name: str
    table: Table
    fields: list[Field] = field(default_factory=list)
    partial_of: str = ""


@dataclass
class Registry:
    """Every generated class, keyed by the doc anchors that point at it."""

    by_anchor: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    names: set[str] = field(default_factory=set)
    models: set[str] = field(default_factory=set)
    partials: set[str] = field(default_factory=set)
    unresolved: dict[str, int] = field(default_factory=dict)

    def partial(self, name: str) -> str:
        """Name of the partial variant of `name`; the docs' own `PartialX` wins if it exists."""
        if name not in self.models:
            return name
        if f"Partial{name}" not in self.names:
            self.partials.add(name)
        return f"Partial{name}"

    def claim(self, name: str, table: Table) -> str:
        """Return a unique class name, prefixing the section name on a clash."""
        if name in self.names:
            name = pascal(strip_suffix(table.container)) + name
        base, n = name, 2
        while name in self.names:
            name, n = f"{base}{n}", n + 1
        self.names.add(name)
        return name

    def register(self, name: str, table: Table, *, section: bool = True) -> None:
        """Point the table's anchors, and (with `section`) its section's anchors, at `name`."""
        target = (table.page, name)
        for anchor in table.anchors:
            self.by_anchor.setdefault((table.page, anchor), target)
        for anchor in table.container_anchors if section else []:
            self.by_anchor.setdefault((table.page, anchor), target)


# --- fetching ---------------------------------------------------------------


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read().decode("utf-8")


def load_page(path: str, *, offline: bool) -> str | None:
    """Return a page's markdown by docs path (`resources/user`), using the cache."""
    cached = CACHE_DIR / f"{path.replace('/', '__')}.md"
    if not offline:
        print(f"fetching {path}")
        cached.write_text(fetch(f"{DOCS_ROOT}/developers/{path}.md"), "utf-8")
    return cached.read_text("utf-8") if cached.exists() else None


# --- text helpers -----------------------------------------------------------


# Code points of the typographic characters the docs use, and their ASCII stand-ins.
ASCII = {
    0x2018: "'",  # left single quotation mark
    0x2019: "'",  # right single quotation mark
    0x201C: '"',  # left double quotation mark
    0x201D: '"',  # right double quotation mark
    0x2013: "-",  # en dash
    0x2014: " - ",  # em dash
    0x2026: "...",  # horizontal ellipsis
    0x00A0: " ",  # no-break space
}


def ascii_text(text: str) -> str:
    """Replace typographic quotes, dashes and spaces, which ruff flags in generated code."""
    return text.translate(ASCII)


def unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text).strip()


def plain(text: str) -> str:
    """Markdown cell to plain text: links become their label, escapes are dropped."""
    text = LINK.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s*\\?\[\d+\\?\]", "", text)  # footnote markers: "gif \[1]"
    return unescape(text).replace("`", "").strip()


def slug(text: str) -> str:
    """Mintlify's heading anchor: lowercase, punctuation dropped, hyphen runs collapsed."""
    text = re.sub(r"[^a-z0-9 -]", "", plain(text).lower())
    return re.sub(r"[\s-]+", "-", text).strip("-")


def pascal(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", plain(text))
    name = "".join(word[:1].upper() + word[1:] for word in words)
    return f"_{name}" if name[:1].isdigit() else name


def strip_suffix(heading: str) -> str:
    return re.sub(r"\s+(structure|object)$", "", plain(heading), flags=re.IGNORECASE)


def identifier(text: str) -> str:
    name = re.sub(r"\W+", "_", plain(text)).strip("_")
    if not name or name[0].isdigit():
        name = f"_{name}"
    return f"{name}_" if keyword.iskeyword(name) else name


def constant(text: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", plain(text))
    return identifier(name).upper()


def docstring(text: str, indent: str = "    ", *, extra: str = "") -> str:
    """Render a docstring, wrapped to the line limit; `extra` is a trailing paragraph."""
    text = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"').strip()
    if not text:
        return ""
    if text.endswith('"'):
        text = text[:-1] + '\\"'
    one_line = f'{indent}"""{text}"""'
    if not extra and len(one_line) <= LINE_LIMIT:
        return one_line
    lines = wrap(text, LINE_LIMIT - len(indent) - 3)
    if extra:
        lines += ["", extra]
    body = "\n".join(f"{indent}{line}" if line else "" for line in lines[1:])
    return f'{indent}"""{lines[0]}\n{body}\n{indent}"""'


# --- parsing ----------------------------------------------------------------


def parse_tables(page: str, markdown: str) -> list[Table]:
    """Collect every table on a page with its heading, section and anchors."""
    tables: list[Table] = []
    stack: list[tuple[int, str]] = []
    lines = markdown.splitlines()
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and (match := HEADING.match(line)):
            level = len(match.group(1))
            stack = [(lvl, text) for lvl, text in stack if lvl < level]
            stack.append((level, match.group(2)))
        elif (
            not in_fence
            and line.startswith("|")
            and i + 1 < len(lines)
            and TABLE_RULE.match(lines[i + 1])
        ):
            header = [plain(cell) for cell in split_row(line)]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            table = make_table(page, stack, header, rows)
            table.footnotes = parse_footnotes(lines, i)
            tables.append(table)
            continue
        i += 1
    return tables


FOOTNOTE = re.compile(r"^((?:\\\*)+)\s+(.+)$")


def parse_footnotes(lines: list[str], start: int) -> dict[int, str]:
    r"""Read the `\\* text` lines that follow a table, skipping blank lines between them."""
    notes: dict[int, str] = {}
    for line in lines[start:]:
        if not line.strip():
            continue
        match = FOOTNOTE.match(line.strip())
        if match is None:
            break
        notes[match.group(1).count("\\*")] = plain(match.group(2))
    return notes


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in CELL_SPLIT.split(line.strip().strip("|"))]


def make_table(
    page: str, stack: list[tuple[int, str]], header: list[str], rows: list[list[str]]
) -> Table:
    heading = stack[-1][1] if stack else ""
    parents = [text for _, text in stack[:-1] if _ > 1]
    container = parents[-1] if parents else ""
    own = slug(heading)
    anchors = [own] + [f"{slug(parent)}-{own}" for parent in parents]
    container_anchors = [slug(container)] if container else []
    return Table(page, heading, container, anchors, container_anchors, header, rows)


def column(table: Table, name: str) -> int | None:
    """Index of the header cell called `name` (case-insensitive), if any."""
    return next((i for i, cell in enumerate(table.header) if cell.lower() == name), None)


def is_model_table(table: Table) -> bool:
    header = [cell.lower() for cell in table.header]
    return header[:2] == ["field", "type"] and not SKIPPED_HEADING.search(plain(table.heading))


def resolve_link(label: str, url: str, page: str, registry: Registry) -> str | None:
    target_url, _, anchor = url.partition("#")
    match = DOC_URL.search(target_url)
    target = match.group(1) if match else (page if not target_url else None)
    if target is None:
        return None
    hit = registry.by_anchor.get((target, anchor)) or registry.by_anchor.get(
        (target, f"{slug(label)}-object")
    )
    return hit[1] if hit else None


def resolve_type(raw: str, page: str, registry: Registry) -> tuple[str, bool]:
    """Turn a docs type cell into `(annotation, nullable)`."""
    text = re.sub(r"\s*\((?![^)]*://)[^)]*\)", "", raw)  # drop "(notes)", keep link urls
    text = unescape(text).rstrip("*").strip()
    nullable = text.startswith("?")
    text = text.removeprefix("?").strip()
    return resolve_inner(text, page, registry), nullable


LIST_OF = re.compile(r"^\[?(?:array|list)\]?(?:\([^)]*\))?\s+of\s+(.*)$", re.IGNORECASE)
PHRASES = [
    (re.compile(r"^array$"), "list[Any]"),
    (re.compile(r"^dictionary with keys in"), "dict[str, str]"),  # locale -> localized text
    (re.compile(r"\bstrings?$"), "str"),  # "[guild feature] strings"
    (re.compile(r"\bids?$"), "Snowflake"),  # "[role] object ids"
]


def resolve_inner(text: str, page: str, registry: Registry) -> str:
    text = re.sub(r"^(an?|the)\s+", "", text, flags=re.IGNORECASE)
    if match := LIST_OF.match(text):
        return f"list[{resolve_inner(match.group(1), page, registry)}]"
    text = re.sub(r"^one of\s+", "", text, flags=re.IGNORECASE)
    lowered = plain(text).lower()
    for pattern, annotation in PHRASES:
        if pattern.search(lowered):
            return annotation
    links = LINK.findall(text)
    names = [resolve_link(label, url, page, registry) for label, url in links]
    if found := [name for name in names if name]:
        if lowered.startswith("partial "):
            found = [registry.partial(name) for name in found]
        return " | ".join(dict.fromkeys(found))
    if annotation := resolve_words(lowered, page, registry, linked=bool(links)):
        return annotation
    registry.unresolved[text] = registry.unresolved.get(text, 0) + 1
    return "dict[str, Any]" if "object" in lowered or links else "Any"


def resolve_words(lowered: str, page: str, registry: Registry, *, linked: bool) -> str | None:
    """Resolve an unlinked type: a primitive, `dict<k, v>`, `X or Y`, or a class by name."""
    words = re.sub(r"\s+(objects?|ids?)$", "", lowered.removeprefix("partial ").strip())
    words = PLURALS.get(words, words)
    if words in PRIMITIVES:
        return PRIMITIVES[words]
    if not linked and (name := pascal(words)) in registry.names:  # "channel object"
        return registry.partial(name) if lowered.startswith("partial ") else name
    if match := re.match(r"^dict<(\w+),\s*(\w+)>$", words):
        key, value = (PRIMITIVES.get(group, "Any") for group in match.groups())
        return f"dict[{key}, {value}]"
    if " or " in words:
        parts = [resolve_inner(part, page, registry) for part in words.split(" or ")]
        return " | ".join(dict.fromkeys(parts))
    return None


def build_model(model: Model, registry: Registry) -> None:
    table = model.table
    desc_col = column(table, "description")
    seen: set[str] = set()
    for row in table.rows:
        if len(row) < 2 or not plain(row[0]):  # noqa: PLR2004
            continue
        raw_name = plain(row[0]).rstrip("*").strip()
        optional = raw_name.endswith("?")
        name = identifier(raw_name.rstrip("?"))
        if name in seen:
            continue
        seen.add(name)
        annotation, nullable = resolve_type(row[1], table.page, registry)
        if nullable or optional:
            annotation = f"{annotation} | None"
        doc = plain(row[desc_col]) if desc_col is not None and len(row) > desc_col else ""
        model.fields.append(Field(name, annotation, optional, doc))


def render_model(item: Model) -> str:
    source = f"{DOCS_ROOT}/developers/{item.table.page}#{item.table.anchors[-1]}"
    summary = f"{plain(item.table.heading)}."
    if item.partial_of:
        summary = f"Partial {item.partial_of}: the same fields, any of which may be missing."
    lines = [
        "@model(kw_only=True)",
        f"class {item.name}:",
        docstring(summary, extra=source),
    ]
    for f in item.fields:
        default = " = None" if f.optional else ""
        lines.append(f"\n    {f.name}: {f.annotation}{default}")
        if f.doc:
            lines.append(docstring(f.doc))
    return "\n".join(lines)


VALUE_COLUMNS = {"value", "integer", "id", "code"}


NAME_ONLY_COLUMNS = {"enum", "feature", "type", "status"}


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


Columns = tuple[int, int] | tuple[int, int, int | None]
"""`(value column, name column)`, plus the column that documents each member if it isn't
`Description`. A name column equal to the value column makes the values their own names."""

Overrides = dict[tuple[str, str], Columns]
"""Enum columns for tables the header-based guess gets wrong, keyed by `(page, heading)`."""

HTTP_CODE = re.compile(r"^(\d{3})\s*\((.+)\)$")
DOC_COLUMNS = ("description", "meaning", "explanation")

RESOURCE_OVERRIDES: Overrides = {("components/reference", "Component Types"): (0, 1, 2)}
"""Enum tables on the resource pages that the header guess misses; every generator that
collects the resource pages passes these, so they all see the same classes."""


def doc_column(table: Table, columns: Columns) -> int | None:
    """Column holding the member docs: the override's, else the first documenting header."""
    if len(columns) == 3:  # noqa: PLR2004
        return columns[2]
    return next((i for name in DOC_COLUMNS if (i := column(table, name)) is not None), None)


def enum_columns(table: Table, overrides: Overrides | None = None) -> Columns | None:
    """Return `(value column, name column)` for an enum table, else `None`."""
    if overrides and (table.page, plain(table.heading)) in overrides:
        return overrides[table.page, plain(table.heading)]
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
    if match := HTTP_CODE.match(text):  # "404 (NOT FOUND)"
        return "int", match.group(1)
    if re.fullmatch(r"-?\d+", text):
        return "int", text
    if match := SHIFT.search(text):  # "1 << 3", or "0x08 (1 << 3)" on the permissions page
        return "flag", f"1 << {match.group(1)}"
    if text and not re.search(r"\s", text):
        return "str", repr(text)
    return None


def build_enum(
    table: Table, columns: Columns, registry: Registry, *, name: str = "", lenient: bool = False
) -> Enum | None:
    """Build an enum from a table; `lenient` skips rows with no usable value (`5xx` ranges)."""
    value_col, name_col = columns[:2]
    desc_col = doc_column(table, columns)
    rows = [row for row in table.rows if len(row) > value_col and plain(row[value_col])]
    parsed = [enum_value(row[value_col]) for row in rows]
    if lenient:
        kept = [(row, value) for row, value in zip(rows, parsed, strict=True) if value is not None]
        rows, parsed = [r for r, _ in kept], [v for _, v in kept]
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
    enum = Enum(registry.claim(name or pascal(table.heading), table), base, table)
    seen: set[str] = set()
    for row, (_, literal) in zip(rows, values, strict=True):
        name_cell = row[name_col].strip("'\"") if len(row) > name_col else ""
        if http := HTTP_CODE.match(plain(name_cell)):
            name_cell = http.group(2)
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


def build_computed(table: Table, columns: Columns, registry: Registry) -> Computed | None:
    """Turn a snowflake-typed table of `param +/- n` values into static methods."""
    value_col, name_col = columns[:2]
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


def module_name(page: str) -> str:
    """`resources/user` -> `user`, `topics/permissions` -> `topics_permissions`."""
    return page.removeprefix("resources/").replace("/", "_").replace("-", "_")


def collect(
    pages: dict[str, str],
    registry: Registry,
    *,
    overrides: Overrides | None = None,
    renames: dict[tuple[str, str], str] | None = None,
    enums_only: set[str] | None = None,
) -> tuple[dict[str, list[Item]], list[Model], list[str]]:
    """Pass 1: name every class and register its anchors, so links resolve in pass 2.

    `overrides` fixes the enum columns of tables the header guess gets wrong; `renames`
    replaces the class name a table's heading would give (keyed by `(page, plain heading)`).
    Pages in `enums_only` contribute their enums but no models.
    """
    per_page: dict[str, list[Item]] = {page: [] for page in pages}
    models: list[Model] = []
    skipped: list[str] = []
    renames = renames or {}
    for page, markdown in pages.items():
        for table in parse_tables(page, markdown):
            renamed = renames.get((page, plain(table.heading)), "")
            if is_model_table(table):
                if enums_only and page in enums_only:  # another generator owns this page's models
                    continue
                name = registry.claim(renamed or pascal(strip_suffix(table.heading)), table)
                registry.register(name, table)
                registry.models.add(name)
                item = Model(name, table)
                models.append(item)
                per_page[page].append(item)
            elif columns := enum_columns(table, overrides):
                fixed = bool(overrides and (page, plain(table.heading)) in overrides)
                item = build_enum(
                    table, columns, registry, name=renamed, lenient=fixed
                ) or build_computed(table, columns, registry)
                if item is None:
                    skipped.append(f"{page}: {plain(table.heading)} (unparseable values)")
                    continue
                # An enum under "Component Object" must not stand for the object itself.
                registry.register(item.name, table, section=not fixed)
                per_page[page].append(item)
    return per_page, models, skipped


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


# --- REST endpoints -----------------------------------------------------------

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PATH_PARAM = re.compile(r"\{([a-z_]+)(?:\.([a-z_]+))?\}")
ROUTE_LINE = re.compile(r"^/[^\s]*$")
PARAM_HEADING = re.compile(r"\b(json|form|query string|query|url)\b.*\bparams?\b", re.IGNORECASE)


@dataclass
class Endpoint:
    """One endpoint section from a resources page: heading, route line and param tables."""

    page: str
    name: str
    method: str
    path: str
    """The route with links stripped and `{channel.id}` kept, e.g. `/channels/{channel.id}`."""
    anchor: str
    description: str = ""
    deprecated: bool = False
    text: str = ""
    """The section's markdown, for notes such as "supports the `X-Audit-Log-Reason` header"."""
    tables: list[Table] = field(default_factory=list)

    @property
    def audit_log_reason(self) -> bool:
        """Whether the section says the endpoint reads `X-Audit-Log-Reason`."""
        return "X-Audit-Log-Reason" in self.text

    @property
    def key(self) -> tuple[str, str]:
        """`(method, path)` with every placeholder reduced to `{}`, to match the OpenAPI spec."""
        return self.method, PATH_PARAM.sub("{}", self.path)

    @property
    def url(self) -> str:
        """Link to the endpoint's section in the docs."""
        return f"{DOCS_ROOT}/developers/{self.page}#{self.anchor}"


def parse_endpoints(page: str, markdown: str) -> list[Endpoint]:
    """Find every `## Name` section whose first lines are an HTTP method and a route."""
    lines = markdown.splitlines()
    tables = parse_tables(page, markdown)
    endpoints: list[Endpoint] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else HEADING.match(line)
        if not heading or len(heading.group(1)) != 2 or i + 3 >= len(lines):  # noqa: PLR2004
            continue
        method = lines[i + 2].strip()
        path = LINK.sub(r"\1", lines[i + 3]).strip()
        if method not in METHODS or not ROUTE_LINE.match(path):
            continue
        name = plain(heading.group(2))
        endpoint = Endpoint(page, name, method, path, slug(name))
        endpoint.deprecated = "(deprecated)" in name.lower()
        end = next(
            (j for j in range(i + 4, len(lines)) if re.match(r"^#{1,2}\s", lines[j])), len(lines)
        )
        body = lines[i + 4 : end]
        endpoint.text = "\n".join(body)
        paragraphs = []
        for text in body:
            if text.startswith(("#", "|", ">", "```")):
                break
            paragraphs.append(text)
        first = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(paragraphs)) if p.strip()]
        endpoint.description = plain(first[0]) if first else ""
        endpoint.tables = [
            t for t in tables if t.heading and slug(t.container or t.heading) == endpoint.anchor
        ]
        endpoints.append(endpoint)
    return endpoints


# --- OpenAPI spec -----------------------------------------------------------

SPEC_URL = "https://raw.githubusercontent.com/discord/discord-api-spec/main/specs/openapi.json"
SPEC_CACHE = REPO_ROOT / ".cache" / "discord-openapi.json"


def load_spec(*, offline: bool) -> dict[str, Any]:
    """Return Discord's OpenAPI spec, downloaded once per run into the cache."""
    SPEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not offline:
        print("fetching openapi.json")
        SPEC_CACHE.write_text(fetch(SPEC_URL), "utf-8")
    if not SPEC_CACHE.exists():
        msg = "the OpenAPI spec is not cached; run without --offline"
        raise SystemExit(msg)
    return json.loads(SPEC_CACHE.read_text("utf-8"))
