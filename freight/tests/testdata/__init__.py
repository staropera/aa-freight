from datetime import timedelta
import inspect
import json
import os
from random import randrange
from unittest.mock import Mock

from django.contrib.auth.models import User, Permission 
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.authentication.models import CharacterOwnership

from ...models import *

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))


def _load_structures_data() -> list:
    with open(
        currentdir + '/universe_structures.json', 
        'r', 
        encoding='utf-8'
    ) as f:
        data = json.load(f)

    return data

def _load_characters_data() -> list:
    with open(currentdir + '/characters.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data


def _load_contract_data() -> list:
    with open(currentdir + '/contracts.json', 'r', encoding='utf-8') as f:
        contracts_data = json.load(f)

    # update dates to something current, so won't be treated as stale
    for contract in contracts_data:
        date_issued = now() - timedelta(
            days=randrange(1), 
            hours=randrange(10)
        )
        date_accepted = date_issued + timedelta(
            hours=randrange(5),
            minutes=randrange(30)
        )
        date_completed = date_accepted + timedelta(
            hours=randrange(12),
            minutes=randrange(30)
        )
        date_expired = now() + timedelta(
            days=randrange(14), 
            hours=randrange(10)
        )
        if 'date_issued' in contract:
            contract['date_issued'] = date_issued.isoformat()

        if 'date_accepted' in contract:
            contract['date_accepted'] = date_accepted.isoformat()

        if 'date_completed' in contract:
            contract['date_completed'] = date_completed.isoformat()

        if 'date_expired' in contract:
            contract['date_expired'] = date_expired.isoformat()

    return contracts_data


contracts_data = _load_contract_data()
characters_data = _load_characters_data()
structures_data = _load_structures_data()


def create_locations():
    jita = Location.objects.create(
        id=60003760,
        name='Jita IV - Moon 4 - Caldari Navy Assembly Plant',
        solar_system_id=30000142,
        type_id=52678,
        category_id=3
    )
    amamake = Location.objects.create(
        id=1022167642188,
        name='Amamake - 3 Time Nearly AT Winners',
        solar_system_id=30002537,
        type_id=35834,
        category_id=65
    ) 
    amarr = Location.objects.create(
        id=60008494,
        name='Amarr VIII (Oris) - Emperor Family Academy',
        solar_system_id=30002187,
        type_id=1932,
        category_id=3
    )
    return jita, amamake, amarr


def create_contract_handler_w_contracts(
    selected_contract_ids: list = None
):
    
    # create characters and entities
    for character in characters_data:
        EveCharacter.objects.create(**character)
        EveCorporationInfo.objects.get_or_create(
            corporation_id=character['corporation_id'],
            defaults={
                'corporation_name': character['corporation_name'],
                'corporation_ticker': character['corporation_ticker'],
                'member_count': 42
            }
        )
        EveEntity.objects.get_or_create(
            id=character['character_id'],                
            defaults={
                'category': EveEntity.CATEGORY_CHARACTER,
                'name': character['character_name'],
            }
        )
        EveEntity.objects.get_or_create(
            id=character['corporation_id'],
            defaults={
                'category': EveEntity.CATEGORY_CORPORATION,
                'name': character['corporation_name'],
            }
        )
        if character['alliance_id'] and character['alliance_id'] != 0:
            EveEntity.objects.get_or_create(
                id=character['alliance_id'],                
                defaults={
                    'category': EveEntity.CATEGORY_ALLIANCE,
                    'name': character['alliance_name'],
                }
            )

    # 1 user
    my_character = EveCharacter.objects.get(character_id=90000001)
    
    my_organization = EveEntity.objects.get(
        id = my_character.alliance_id
    )
    
    my_user = User.objects.create_user(
        my_character.character_name,
        'abc@example.com',
        'password'
    )

    # user needs basic permission to access the app
    p = Permission.objects.get(
        codename='basic_access', 
        content_type__app_label='freight'
    )
    my_user.user_permissions.add(p)
    my_user.save()

    my_main_ownership = CharacterOwnership.objects.create(
        character=my_character,
        owner_hash='x1',
        user=my_user
    )
    my_user.profile.main_character = my_character
    my_user.profile.save()

    my_handler = ContractHandler.objects.create(
        organization=my_organization,
        character=my_main_ownership            
    )

    create_locations()
    
    for contract in contracts_data:
        if (not selected_contract_ids 
            or contract['contract_id'] in selected_contract_ids
        ):
            if contract['type'] == 'courier':
                Contract.objects.update_or_create_from_dict(
                    handler=my_handler,
                    contract=contract,
                    esi_client=Mock()
                )

    return my_user
