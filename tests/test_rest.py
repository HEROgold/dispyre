"""The generated REST layer: route table, typed client and discriminated unions."""

from __future__ import annotations

import asyncio
import re
import typing
from typing import TYPE_CHECKING, Any

import pytest

from dispyre.decode import decode, encode
from dispyre.discord.resources._types import Snowflake
from dispyre.discord.rest import ROUTES, RestApi, Route
from dispyre.discord.rest import schemas as S  # noqa: N812
from dispyre.discord.topics import OAuth2Scope

if TYPE_CHECKING:
    from collections.abc import Mapping


class Recorder(RestApi):
    """A client that records what it was asked to send and answers with canned data."""

    def __init__(self, answer: object = None) -> None:
        self.answer = answer
        self.sent: list[dict[str, Any]] = []

    async def request(  # noqa: PLR0913
        self,
        route: Route,
        *,
        path: Mapping[str, Any],
        query: Mapping[str, Any],
        body: object = None,
        files: Mapping[str, bytes] | None = None,  # noqa: ARG002
        reason: str | None = None,
    ) -> object:
        self.sent.append(
            {
                "route": route,
                "path": dict(path),
                "query": dict(query),
                "body": body,
                "reason": reason,
            }
        )
        return self.answer


def test_route_table_is_complete() -> None:
    assert len(ROUTES) > 250  # noqa: PLR2004
    assert all(key == route.operation_id for key, route in ROUTES.items())
    assert sum(route.source == "docs" for route in ROUTES.values()) >= 1
    assert all(route.docs for route in ROUTES.values() if route.summary)


@pytest.mark.parametrize("route", ROUTES.values(), ids=lambda r: r.operation_id)
def test_route_is_consistent(route: Route) -> None:
    placeholders = re.findall(r"\{(\w+)\}", route.path)
    assert list(route.path_params) == placeholders
    assert set(route.required_query) <= set(route.query)
    assert route.bot or route.oauth2 or route.anonymous
    assert hasattr(RestApi, route.operation_id)


def test_oauth2_scopes_are_documented_scopes() -> None:
    known = {scope.value for scope in OAuth2Scope}
    used = {scope for route in ROUTES.values() for scope in route.oauth2_scopes}
    assert used <= known, used - known


def test_url_fills_the_path() -> None:
    route = ROUTES["list_messages"]
    assert route.url(channel_id="123") == "https://discord.com/api/v10/channels/123/messages"
    assert ROUTES["get_my_user"].url(base="http://x") == "http://x/users/@me"
    with pytest.raises(KeyError, match="channel_id"):
        route.url()


def test_client_sends_path_and_query_without_unset_values() -> None:
    api = Recorder(answer=[])
    assert asyncio.run(api.list_messages(Snowflake("5"), limit=3)) == []
    (sent,) = api.sent
    assert sent["route"] is ROUTES["list_messages"]
    assert sent["path"] == {"channel_id": "5"}
    assert sent["query"] == {"limit": 3}


def test_client_encodes_the_body_and_passes_the_reason() -> None:
    api = Recorder()
    body = S.MessageCreateRequest(content="hi")
    asyncio.run(api.create_message(Snowflake("5"), body=body))
    (sent,) = api.sent
    assert sent["body"] == {"content": "hi"}
    assert ROUTES["create_message"].multipart


def test_empty_responses_return_none() -> None:
    api = Recorder()
    assert asyncio.run(api.delete_message(Snowflake("5"), Snowflake("6"))) is None


def test_union_members_decode_by_their_type_field() -> None:
    hints = typing.get_type_hints(S.MessageCreateRequest)
    row = {"type": 1, "components": [{"type": 2, "style": 1, "custom_id": "go", "label": "Go"}]}
    section = {
        "type": 9,
        "components": [{"type": 10, "content": "hi"}],
        "accessory": {"type": 2, "style": 5, "url": "https://example.com", "label": "Open"},
    }
    decoded = decode(hints["components"], [row, section])
    assert isinstance(decoded[0], S.ActionRowComponentForMessageRequest)
    assert isinstance(decoded[0].components[0], S.ButtonComponentForMessageRequest)
    assert isinstance(decoded[1], S.SectionComponentForMessageRequest)
    assert isinstance(decoded[1].accessory, S.ButtonComponentForMessageRequest)


def test_a_field_with_another_json_key_round_trips() -> None:
    errors = decode(S.InnerErrors, {"_errors": [{"code": 5, "message": "bad"}]})
    assert errors.errors[0].message == "bad"
    assert encode(errors) == {"_errors": [{"code": 5, "message": "bad"}]}
