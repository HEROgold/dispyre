"""Tests for `dispyre.decode.from_dict` on hand-made and generated models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum, IntFlag

from dispyre.decode import from_dict
from dispyre.discord.resources import (
    ApplicationCommandPermissionsConstants,
    AvatarDecorationData,
    Invite,
    PartialGuild,
    User,
)
from dispyre.discord.resources._types import Snowflake, snowflake_time


class Color(IntEnum):
    RED = 1
    BLUE = 2


class Perm(IntFlag):
    READ = 1 << 0
    WRITE = 1 << 1


@dataclass(kw_only=True)
class Leaf:
    name: str


@dataclass(kw_only=True)
class Other:
    size: int


@dataclass(kw_only=True)
class Root:
    leaf: Leaf
    leaves: list[Leaf] | None = None
    color: Color | None = None
    perm: Perm | None = None
    either: Leaf | Other | None = None
    count: int | None = None
    global_: bool | None = None


def test_nested_models_lists_and_enums() -> None:
    root = from_dict(
        Root,
        {"leaf": {"name": "a"}, "leaves": [{"name": "b"}], "color": 2, "perm": 3},
    )
    assert root.leaf == Leaf(name="a")
    assert root.leaves == [Leaf(name="b")]
    assert root.color is Color.BLUE
    assert root.perm == Perm.READ | Perm.WRITE


def test_unknown_values_and_keys_are_tolerated() -> None:
    root = from_dict(Root, {"leaf": {"name": "a", "new_api_field": 1}, "color": 99, "perm": 8})
    assert root.color == 99  # unknown enum value kept raw  # noqa: PLR2004
    assert root.perm == 8  # IntFlag keeps unknown bits  # noqa: PLR2004


def test_union_picks_the_model_whose_required_keys_are_present() -> None:
    leaf = {"name": "a"}
    assert from_dict(Root, {"leaf": leaf, "either": {"size": 3}}).either == Other(size=3)
    assert from_dict(Root, {"leaf": leaf, "either": {"name": "x"}}).either == Leaf(name="x")


def test_keyword_field_and_numeric_string() -> None:
    root = from_dict(Root, {"leaf": {"name": "a"}, "global": True, "count": "12"})
    assert root.global_ is True
    assert root.count == 12  # noqa: PLR2004


# Example payload from https://docs.discord.com/developers/resources/user#user-object
USER = {
    "id": "80351110224678912",
    "username": "Nelly",
    "global_name": None,
    "discriminator": "1337",
    "avatar": "8342729096ea3675442027381ff50dfe",
    "flags": 64,
    "avatar_decoration_data": {
        "sku_id": "1144058844004233369",
        "asset": "a_fed43ab12698df65902ba06727e20c0e",
    },
}


def test_generated_user_decodes_nested_data() -> None:
    user = from_dict(User, USER)
    assert isinstance(user.avatar_decoration_data, AvatarDecorationData)
    assert user.id == Snowflake("80351110224678912")
    assert user.flags == 64  # stays an int by design  # noqa: PLR2004


def test_partial_guild_accepts_a_subset_of_fields() -> None:
    invite = from_dict(
        Invite,
        {
            "type": 0,
            "code": "0vCdhLbwjZZTWZLD",
            "guild": {"id": "165176875973476352", "name": "CS:GO Fraggers Only"},
            "channel": None,
            "expires_at": None,
        },
    )
    assert isinstance(invite.guild, PartialGuild)
    assert invite.guild.name == "CS:GO Fraggers Only"
    assert invite.guild.owner_id is None


def test_snowflake_time() -> None:
    # Example from https://docs.discord.com/developers/reference#snowflakes
    created = snowflake_time(Snowflake("175928847299117063"))
    assert created == datetime(2016, 4, 30, 11, 18, 25, 796000, tzinfo=UTC)


def test_computed_permission_constants() -> None:
    guild_id = Snowflake("41771983423143937")
    assert ApplicationCommandPermissionsConstants.everyone(guild_id) == guild_id
    assert ApplicationCommandPermissionsConstants.all_channels(guild_id) == Snowflake(
        "41771983423143936"
    )
