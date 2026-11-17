# Dispyre

Opinionated, personal discord api wrapper + framework

## Installation

```bash
git clone https://github.com/HEROgold/dispyre.git
cd dispyre
uv sync
```

## Usage

```python
import dispyre
```

## Development

```bash
uv sync
uv run prek install
just check   # lint + typecheck + test
```

See `justfile` (`just --list`) for all available tasks; every recipe wraps a
plain Python script under `scripts/`, so `uv run scripts/<name>.py` always
works even without `just` installed.

## Documentation

Docs are built with [Zensical](https://zensical.org) from `docs/`. Preview
locally with `just docs`.

## License

Custom non-commercial license — see [LICENSE](LICENSE). Commercial use
requires explicit written permission.
