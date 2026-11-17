"""Generic HTTP client interface and response representation."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

K = TypeVar("K", bound=Any)
V = TypeVar("V", bound=Any)


@dataclass(frozen=True)
class HttpResponse(Generic[K, V]):
    status_code: int
    headers: Mapping[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Mapping[K, V]:
        return json.loads(self.text)


class AbstractHttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
        timeout: float | None = None,
    ) -> HttpResponse: ...
