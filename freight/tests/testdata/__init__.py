import inspect
import json
import os
from datetime import datetime, timedelta
from random import randrange
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.django import app_labels

from ...models import Contract, ContractHandler, EveEntity, Location

if "discord" in app_labels():
    from allianceauth.services.modules.discord.models import DiscordUser


currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


def _load_structures_data() -> list:
    with open(currentdir + "/universe_structures.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def _load_characters_data() -> list:
    with open(currentdir + "/characters.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def _load_contract_data() -> list:
    with open(currentdir + "/contracts.json", "r", encoding="utf-8") as f:
        contracts_data = json.load(f)

    # update dates to something current, so won't be treated as stale
    for contract in contracts_data:
        date_issued = now() - timedelta(hours=12, minutes=randrange(30))
        date_accepted = date_issued + timedelta(hours=2, minutes=randrange(30))
        date_completed = date_accepted + timedelta(hours=3, minutes=randrange(30))
        date_expired = now() + timedelta(days=7 + randrange(7), hours=randrange(10))
        if "date_issued" in contract:
            contract["date_issued"] = date_issued

        if "date_accepted" in contract:
            contract["date_accepted"] = date_accepted

        if "date_completed" in contract:
            contract["date_completed"] = date_completed

        if "date_expired" in contract:
            contract["date_expired"] = date_expired

    return contracts_data


contracts_data = _load_contract_data()
characters_data = _load_characters_data()
structures_data = _load_structures_data()


def create_locations():
    jita = Location.objects.create(
        id=60003760,
        name="Jita IV - Moon 4 - Caldari Navy Assembly Plant",
        solar_system_id=30000142,
        type_id=52678,
        category_id=3,
    )
    amamake = Location.objects.create(
        id=1022167642188,
        name="Amamake - 3 Time Nearly AT Winners",
        solar_system_id=30002537,
        type_id=35834,
        category_id=65,
    )
    amarr = Location.objects.create(
        id=60008494,
        name="Amarr VIII (Oris) - Emperor Family Academy",
        solar_system_id=30002187,
        type_id=1932,
        category_id=3,
    )
    return jita, amamake, amarr


def create_user_from_character(character: EveCharacter) -> User:
    user = AuthUtils.create_user(username=character.character_name)
    user.profile.main_character = character
    user.profile.save()
    return user


def create_entities_from_characters():
    for character in characters_data:
        EveCharacter.objects.create(**character)
        EveCorporationInfo.objects.get_or_create(
            corporation_id=character["corporation_id"],
            defaults={
                "corporation_name": character["corporation_name"],
                "corporation_ticker": character["corporation_ticker"],
                "member_count": 42,
            },
        )
        EveEntity.objects.get_or_create(
            id=character["character_id"],
            defaults={
                "category": EveEntity.Category.CHARACTER,
                "name": character["character_name"],
            },
        )
        EveEntity.objects.get_or_create(
            id=character["corporation_id"],
            defaults={
                "category": EveEntity.Category.CORPORATION,
                "name": character["corporation_name"],
            },
        )
        if "alliance_id" in character and character["alliance_id"] is not None:
            EveEntity.objects.get_or_create(
                id=character["alliance_id"],
                defaults={
                    "category": EveEntity.Category.ALLIANCE,
                    "name": character["alliance_name"],
                },
            )


def _convert_eve_date_str_to_dt(date_str) -> datetime:
    return datetime.strptime("%Y-%m-%dT%H:%M:%S%Z", date_str) if date_str else None


def create_contract_handler_w_contracts(selected_contract_ids: list = None) -> tuple:
    """create contract handler with contracts and all related entities"""

    create_entities_from_characters()

    # 1 user
    my_character = EveCharacter.objects.get(character_id=90000001)
    my_organization = EveEntity.objects.get(id=my_character.alliance_id)
    User.objects.filter(username=my_character.character_name).delete()
    my_user = AuthUtils.create_user(my_character.character_name)
    my_user = AuthUtils.add_permission_to_user_by_name("freight.basic_access", my_user)
    my_main_ownership = CharacterOwnership.objects.create(
        character=my_character, owner_hash="x1", user=my_user
    )
    my_user.profile.main_character = my_character
    my_user.profile.save()
    my_user = User.objects.get(username=my_character.character_name)
    my_handler = ContractHandler.objects.create(
        organization=my_organization, character=my_main_ownership
    )

    create_locations()

    for contract in contracts_data:
        if (
            not selected_contract_ids
            or contract["contract_id"] in selected_contract_ids
        ):
            if contract["type"] == "courier":
                Contract.objects.update_or_create_from_dict(
                    handler=my_handler, contract=contract, token=Mock()
                )

    # create users and Discord accounts from contract issuers
    has_discord = "discord" in app_labels()
    for contract in Contract.objects.all():
        issuer_user = User.objects.filter(
            character_ownerships__character=contract.issuer
        ).first()
        if not issuer_user:
            issuer_user = User.objects.create_user(
                contract.issuer.character_name, "abc@example.com", "password"
            )
            CharacterOwnership.objects.create(
                character=contract.issuer,
                owner_hash=contract.issuer.character_name + "x",
                user=issuer_user,
            )

        if has_discord:
            DiscordUser.objects.update_or_create(
                user=issuer_user, defaults={"uid": contract.issuer.character_id}
            )

    return my_handler, my_user
