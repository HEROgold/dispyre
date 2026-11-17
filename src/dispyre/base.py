"""Abstract bases for dispyre."""

from typing import TYPE_CHECKING

from dispyre._compat import HAS_PYDANTIC

if TYPE_CHECKING:
    from dataclasses import dataclass as model
elif HAS_PYDANTIC:
    from pydantic.dataclasses import dataclass as model
else:
    from dataclasses import dataclass as model  # noqa: F401
