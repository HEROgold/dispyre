"""The generated gateway event registry and the docs' JSON examples."""

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, get_args

import pytest

from dispyre.decode import decode
from dispyre.discord.events import (
    RECEIVE_EVENTS,
    SEND_EVENTS,
    EventInfo,
    GatewayIntents,
    MessageCreate,
    ReceiveEvent,
    SendEvent,
)
from dispyre.discord.resources.message import Message

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

EXAMPLES = json.loads(
    (Path(__file__).parent / "fixtures" / "gateway_event_examples.json").read_text("utf-8")
)
CASES = [
    pytest.param(SEND_EVENTS[SendEvent(key)], payload, id=f"send-{key}")
    for key, payload in EXAMPLES["send"].items()
] + [
    pytest.param(RECEIVE_EVENTS[ReceiveEvent(key)], payload, id=f"receive-{key}")
    for key, payload in EXAMPLES["receive"].items()
]


def test_every_event_has_info() -> None:
    assert set(SEND_EVENTS) == set(SendEvent)
    assert set(RECEIVE_EVENTS) == set(ReceiveEvent)


def test_wire_names_follow_the_docs() -> None:
    assert ReceiveEvent.CHANNEL_CREATE == "CHANNEL_CREATE"
    assert RECEIVE_EVENTS[ReceiveEvent.HELLO].op == 10  # noqa: PLR2004
    assert SEND_EVENTS[SendEvent.IDENTIFY].op == 2  # noqa: PLR2004


def test_intents_come_from_the_gateway_page() -> None:
    assert GatewayIntents.GUILDS == 1 << 0
    assert GatewayIntents.MESSAGE_CONTENT == 1 << 15
    create = RECEIVE_EVENTS[ReceiveEvent.MESSAGE_CREATE]
    assert GatewayIntents.GUILD_MESSAGES in create.intents
    assert GatewayIntents.DIRECT_MESSAGES in create.intents
    assert RECEIVE_EVENTS[ReceiveEvent.HELLO].intents == ()


def members(payload: object) -> "list[type[DataclassInstance]]":
    """Return the dataclasses a payload can be: the class itself, or each class of a union."""
    options = get_args(payload) or (payload,)
    return [
        option
        for option in options
        if isinstance(option, type) and dataclasses.is_dataclass(option)
    ]


@pytest.mark.parametrize(("info", "example"), CASES)
def test_docs_example_keys_are_fields(info: EventInfo, example: object) -> None:
    """Every key in the docs' example is a field of one of the event's payload classes.

    The examples leave out fields the docs mark as required, so this does not build instances.
    """
    classes = members(info.payload)
    if not classes or not isinstance(example, dict):
        pytest.skip("payload is not a model")
    keys = set(example)
    assert any(keys <= {f.name for f in dataclasses.fields(cls)} for cls in classes)


def test_hello_decodes() -> None:
    hello = decode(RECEIVE_EVENTS[ReceiveEvent.HELLO].payload, {"heartbeat_interval": 45000})
    assert hello.heartbeat_interval == 45000  # noqa: PLR2004


def test_message_create_extends_message() -> None:
    assert issubclass(MessageCreate, Message)
    assert RECEIVE_EVENTS[ReceiveEvent.MESSAGE_UPDATE].payload is MessageCreate
