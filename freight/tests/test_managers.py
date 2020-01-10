import datetime
import inspect
import json
import os
import sys
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.authentication.models import CharacterOwnership
from allianceauth.services.modules.discord.models import DiscordUser
from bravado.exception import HTTPNotFound, HTTPForbidden
from esi.clients import SwaggerClient

from . import  _set_logger
from ..app_settings import *
from ..models import *
from .. import tasks


logger = _set_logger('freight.managers', __file__)

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))

    
class TestEveEntityManager(TestCase):
    
    @classmethod
    def setUpClass(cls):
        super(TestEveEntityManager, cls).setUpClass()

        # Eve characters
        with open(
            currentdir + '/testdata/characters.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            characters_data = json.load(f)

        esi_data = dict()
        for character in characters_data:
            esi_data[character['character_id']] = {
                'id': character['character_id'],
                'category': EveEntity.CATEGORY_CHARACTER,
                'name': character['character_name']
            }
            esi_data[character['corporation_id']] = {
                'id': character['corporation_id'],
                'category': EveEntity.CATEGORY_CORPORATION,
                'name': character['corporation_name']
            }
            esi_data[character['alliance_id']] = {
                'id': character['alliance_id'],
                'category': EveEntity.CATEGORY_ALLIANCE,
                'name': character['alliance_name']
            }
            EveCharacter.objects.create(**character)

        cls.esi_data = esi_data

    
    @classmethod
    def esi_post_universe_names(cls, *args, **kwargs) -> list:
        response = list()
        if 'ids' not in kwargs:
            raise ValueError('missing parameter: ids')
        for id in kwargs['ids']:
            if id in cls.esi_data:
                response.append(cls.esi_data[id])
        
        m = Mock()
        m.result.return_value = response
        return m

    @patch('esi.clients.SwaggerClient')
    def test_character_basics(self, SwaggerClient):
        SwaggerClient.from_spec.return_value\
            .Universe.post_universe_names.side_effect = \
                TestEveEntityManager.esi_post_universe_names

        entity, created = EveEntity.objects.get_or_create_from_esi(id=90000001)
        self.assertTrue(created)
        self.assertEqual(
            str(entity),
            'Bruce Wayne'
        )
        self.assertFalse(entity.is_alliance)
        self.assertFalse(entity.is_corporation)
        self.assertTrue(entity.is_character)
        self.assertEqual(
            entity.avatar_url,
            'https://imageserver.eveonline.com/Character/90000001_128.png'
        )

        entity, created = EveEntity.objects.get_or_create_from_esi(id=90000001)
        self.assertFalse(created)

    @patch('esi.clients.SwaggerClient')
    def test_corporation_basics(self, SwaggerClient):
        SwaggerClient.from_spec.return_value\
            .Universe.post_universe_names.side_effect = \
                TestEveEntityManager.esi_post_universe_names

        entity, _ = EveEntity.objects.get_or_create_from_esi(id=92000001)
        self.assertEqual(
            str(entity),
            'Wayne Enterprise'
        )
        self.assertFalse(entity.is_alliance)
        self.assertTrue(entity.is_corporation)
        self.assertFalse(entity.is_character)
        self.assertEqual(
            entity.avatar_url,
            'https://imageserver.eveonline.com/Corporation/92000001_128.png'
        )

    @patch('esi.clients.SwaggerClient')
    def test_alliance_basics(self, SwaggerClient):
        SwaggerClient.from_spec.return_value\
            .Universe.post_universe_names.side_effect = \
                TestEveEntityManager.esi_post_universe_names

        entity, _ = EveEntity.objects.get_or_create_from_esi(id=93000001)
        self.assertEqual(
            str(entity),
            'Justice League'
        )
        self.assertTrue(entity.is_alliance)
        self.assertFalse(entity.is_corporation)
        self.assertFalse(entity.is_character)
        self.assertEqual(
            entity.avatar_url,
            'https://imageserver.eveonline.com/Alliance/93000001_128.png'
        )


    @patch('esi.clients.SwaggerClient')
    def test_alliance_basics(self, SwaggerClient):
        SwaggerClient.from_spec.return_value\
            .Universe.post_universe_names.side_effect = \
                TestEveEntityManager.esi_post_universe_names

        with self.assertRaises(ObjectNotFound):
            entity, _ = EveEntity.objects.get_or_create_from_esi(id=666)
        

    def test_get_category_for_operation_mode(self):
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_MY_ALLIANCE
            ),
            EveEntity.CATEGORY_ALLIANCE
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_MY_CORPORATION
            ),
            EveEntity.CATEGORY_CORPORATION
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
            ),
            EveEntity.CATEGORY_CORPORATION
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_CORP_PUBLIC
            ),
            EveEntity.CATEGORY_CORPORATION
        )

    def test_update_or_create_from_evecharacter(self):       
        character = EveCharacter.objects.get(character_id=90000001)
        corporation, _ = \
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category=EveEntity.CATEGORY_CORPORATION
            )
        self.assertEqual(
            int(corporation.id), 
                92000001            
        )
        alliance, _ = \
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category=EveEntity.CATEGORY_ALLIANCE
            )
        self.assertEqual(
            int(alliance.id), 
            93000001
        )
        char2, _ = \
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category=EveEntity.CATEGORY_CHARACTER
            )
        self.assertEqual(
            int(char2.id),
            90000001
        )
        with self.assertRaises(ValueError):
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category='xxx'
            )


class TestLocationManager(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestLocationManager, cls).setUpClass()

        # Eve characters
        with open(
            currentdir + '/testdata/universe_structures.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.universe_structures = json.load(f)

    
    @classmethod
    def get_universe_stations_station_id(cls, *args, **kwargs) -> dict:    
        if 'station_id' not in kwargs:
            raise ValueError('missing parameter: station_id')
        
        station_id = str(kwargs['station_id'])
        if station_id not in cls.universe_structures:
            raise HTTPNotFound
        else:                
            m = Mock()
            m.result.return_value = cls.universe_structures[station_id]
            return m

    @classmethod
    def get_universe_structures_structure_id(cls, *args, **kwargs) -> dict:    
        if 'structure_id' not in kwargs:
            raise ValueError('missing parameter: structure_id')
        
        structure_id = str(kwargs['structure_id'])
        if structure_id not in cls.universe_structures:
            raise HTTPNotFound
        else:                
            m = Mock()
            m.result.return_value = cls.universe_structures[structure_id]
            return m
            

    def test_update_or_create_from_esi_structure_normal(self):
        esi_client = Mock()
        esi_client.Universe.get_universe_structures_structure_id.side_effect = \
            self.get_universe_structures_structure_id

        obj, created = Location.objects.update_or_create_from_esi(
            esi_client,
            1000000000001
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 1000000000001)        

        obj, created = Location.objects.update_or_create_from_esi(
            esi_client,
            1000000000001
        )        
        self.assertFalse(created)

    def test_update_or_create_from_esi_structure_forbidden(self):
        esi_client = Mock()
        esi_client.Universe.get_universe_structures_structure_id.side_effect = \
            HTTPForbidden(Mock())

        with self.assertRaises(HTTPForbidden):
            Location.objects.update_or_create_from_esi(
                esi_client,
                42,
                add_unknown=False
            )

        obj, created = Location.objects.update_or_create_from_esi(
            esi_client,
            42,
            add_unknown=True
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 42)
        
        
    def test_update_or_create_from_esi_station_normal(self):
        esi_client = Mock()
        esi_client.Universe.get_universe_stations_station_id.side_effect = \
            self.get_universe_stations_station_id

        obj, created = Location.objects.update_or_create_from_esi(
            esi_client,
            60000001
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 60000001)        

        obj, created = Location.objects.update_or_create_from_esi(
            esi_client,
            60000001
        )        
        self.assertFalse(created)


    def test_update_or_create_from_esi_station_forbidden(self):
        esi_client = Mock()
        esi_client.Universe.get_universe_stations_station_id.side_effect = \
            HTTPNotFound(Mock())

        with self.assertRaises(HTTPNotFound):
            Location.objects.update_or_create_from_esi(
                esi_client,
                60000001,
                add_unknown=False
            )
