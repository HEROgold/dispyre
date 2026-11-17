"""The generated enums, constants and registries from the topic, reference and webhook pages."""

from __future__ import annotations

from dispyre.discord import topics
from dispyre.discord.resources import Entitlement
from dispyre.discord.resources._types import Snowflake
from dispyre.discord.resources.components_reference import Button, ComponentTypes
from dispyre.discord.topics import (
    CALLBACK_DATA_BY_TYPE,
    COMPONENT_BY_TYPE,
    GLOBAL_REQUESTS_PER_SECOND,
    INTERACTION_DATA_BY_TYPE,
    INVALID_REQUEST_LIMIT,
    VOICE_PAYLOADS,
    WEBHOOK_EVENT_PAYLOADS,
    EncryptionMode,
    GatewayCloseEventCodes,
    GatewayOpcodes,
    HTTPStatusCode,
    Locale,
    OAuth2Scope,
    RateLimitHeader,
    RateLimitScope,
    RPCCommands,
    RPCOpcodes,
    VoiceIdentify,
    VoiceOpcodes,
    WebhookEventType,
    decode_component,
)


def test_opcodes_and_status_codes() -> None:
    assert GatewayOpcodes.HELLO == 10  # noqa: PLR2004
    assert VoiceOpcodes.SELECT_PROTOCOL == 1
    assert GatewayCloseEventCodes.AUTHENTICATION_FAILED == 4004  # noqa: PLR2004
    assert HTTPStatusCode.NOT_FOUND == 404  # noqa: PLR2004
    assert HTTPStatusCode.TOO_MANY_REQUESTS == 429  # noqa: PLR2004
    assert RPCOpcodes.HANDSHAKE == 0


def test_json_error_codes_keep_their_numbers() -> None:
    assert topics.JSONErrorCodes.UNKNOWN_ACCOUNT == 10001  # noqa: PLR2004


def test_locales_and_scopes_are_strings() -> None:
    assert Locale("en-US") is Locale.ENGLISH_US
    assert OAuth2Scope.IDENTIFY == "identify"
    assert "bot" in {scope.value for scope in OAuth2Scope}
    assert RPCCommands.AUTHORIZE == "AUTHORIZE"


def test_rate_limit_constants() -> None:
    assert RateLimitHeader.BUCKET == "X-RateLimit-Bucket"
    assert {scope.value for scope in RateLimitScope} == {"user", "global", "shared"}
    assert GLOBAL_REQUESTS_PER_SECOND == 50  # noqa: PLR2004
    assert INVALID_REQUEST_LIMIT == 10_000  # noqa: PLR2004


def test_voice_payloads_follow_the_examples() -> None:
    assert VOICE_PAYLOADS[VoiceOpcodes.IDENTIFY] == (VoiceIdentify,)
    identify = VoiceIdentify(
        server_id=Snowflake("1"),
        user_id=Snowflake("2"),
        session_id="s",
        token="t",  # noqa: S106
        max_dave_protocol_version=1,
    )
    assert identify.server_id == "1"
    assert EncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE == "aead_xchacha20_poly1305_rtpsize"


def test_every_webhook_event_type_has_a_payload() -> None:
    assert set(WEBHOOK_EVENT_PAYLOADS) == set(WebhookEventType)
    assert WEBHOOK_EVENT_PAYLOADS[WebhookEventType.ENTITLEMENT_CREATE] is Entitlement


def test_classes_by_component_type() -> None:
    assert COMPONENT_BY_TYPE[ComponentTypes.BUTTON] is Button
    assert decode_component({"type": 2, "style": 1, "custom_id": "go"}) == Button(
        type=2, style=1, custom_id="go"
    )
    assert decode_component({"type": 999}) == {"type": 999}


def test_classes_by_interaction_type() -> None:
    assert INTERACTION_DATA_BY_TYPE[2].__name__ == "ApplicationCommandData"
    assert CALLBACK_DATA_BY_TYPE[9].__name__ == "Modal"
