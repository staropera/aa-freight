import datetime
import inspect
import json
import os
import sys
from unittest.mock import Mock, patch

from dhooks_lite import Embed

from django.contrib.auth.models import User, Permission 
from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.authentication.models import CharacterOwnership
from esi.models import Token

from . import _set_logger
from ..app_settings import *
from ..models import *
from .. import tasks

logger = _set_logger('freight.models', __file__)

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))

    
class TestPricing(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestPricing, cls).setUpClass()
        
        # Eve characters
        with open(
            currentdir + '/testdata/characters.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.characters_data = json.load(f)

    def setUp(self):
        for character in self.characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character['corporation_id'],
                defaults={
                    'corporation_name': character['corporation_name'],
                    'corporation_ticker': character['corporation_ticker'],
                    'member_count': 42
                }
            )
        
        # 1 user
        character = EveCharacter.objects.get(character_id=90000001)
        
        alliance = EveEntity.objects.create(
            id = character.alliance_id,
            category = EveEntity.CATEGORY_ALLIANCE,
            name = character.alliance_name
        )
        
        self.handler = ContractHandler.objects.create(
            organization=alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE
        )

        self.location_1 = Location.objects.create(
            id=60003760,
            name='Jita IV - Moon 4 - Caldari Navy Assembly Plant',
            solar_system_id=30000142,
            type_id=52678,
            category_id=3
        )
        self.location_2 = Location.objects.create(
            id=1022167642188,
            name='Amamake - 3 Time Nearly AT Winners',
            solar_system_id=30002537,
            type_id=35834,
            category_id=65
        )      

    @patch('freight.models.FREIGHT_FULL_ROUTE_NAMES', False)
    def test_name_short(self):        
        p = Pricing(
            start_location = self.location_1,
            end_location = self.location_2,
            price_base = 50000000
        )
        self.assertEqual(
            p.name,
            'Jita <-> Amamake'
        )

    @patch('freight.models.FREIGHT_FULL_ROUTE_NAMES', True)
    def test_name_full(self):        
        p = Pricing(
            start_location = self.location_1,
            end_location = self.location_2,
            price_base = 50000000
        )
        self.assertEqual(
            p.name,            
            'Jita IV - Moon 4 - Caldari Navy Assembly Plant <-> ' \
                + 'Amamake - 3 Time Nearly AT Winners'
        )


    def test_get_calculated_price(self):
        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, 0), 
            500
        )

        p = Pricing()        
        p.price_per_collateral_percent = 2
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            20
        )

        p = Pricing()        
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            520
        )

        p = Pricing()
        p.price_base = 20
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            20
        )

        p = Pricing()
        p.price_min = 1000
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            1000
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            520
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_min = 1000
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            1000
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        p.price_min = 500
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            540
        )

        with self.assertRaises(ValueError):            
            p.get_calculated_price(-5, 0)

        with self.assertRaises(ValueError):            
            p.get_calculated_price(50, -5)

        p = Pricing()
        p.price_base = 0    
        self.assertEqual(
            p.get_calculated_price(None, None),
            0
        )

        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, None),
            500
        )

        p = Pricing()
        p.price_per_collateral_percent = 2
        self.assertEqual(
            p.get_calculated_price(None, 100),
            2
        )

    
    def test_get_contract_pricing_errors(self):
        p = Pricing()
        p.price_base = 50
        self.assertIsNone(p.get_contract_price_check_issues(10, 20, 50))
                
        p = Pricing()
        p.price_base = 500
        p.volume_max = 300        
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 1000))

        p = Pricing()
        p.price_base = 500
        p.volume_min = 100
        self.assertIsNotNone(p.get_contract_price_check_issues(50, 1000))

        p = Pricing()
        p.price_base = 500
        p.collateral_max = 300        
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 1000))

        p = Pricing()
        p.price_base = 500
        p.collateral_min = 300        
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 200))

        p = Pricing()
        p.price_base = 500        
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 200, 400))
        
        p = Pricing()
        p.price_base = 500
        with self.assertRaises(ValueError):            
            p.get_contract_price_check_issues(-5, 0)

        with self.assertRaises(ValueError):            
            p.get_contract_price_check_issues(50, -5)

        with self.assertRaises(ValueError):            
            p.get_contract_price_check_issues(50, 5, -5)
        

    def test_collateral_min_allows_zero(self):
        p = Pricing()
        p.price_base = 500
        p.collateral_min = 0
        self.assertIsNone(p.get_contract_price_check_issues(350, 0))

    def test_collateral_min_allows_none(self):
        p = Pricing()
        p.price_base = 500        
        self.assertIsNone(p.get_contract_price_check_issues(350, 0))

    def test_zero_collateral_allowed_for_collateral_pricing(self):
        p = Pricing()        
        p.collateral_min = 0
        p.price_base = 500
        p.price_per_collateral_percent = 2
        self.assertIsNone(p.get_contract_price_check_issues(350, 0))
        self.assertEqual(
            p.get_calculated_price(350, 0),
            500
        )

    def test_price_per_volume_modifier_none_if_not_set(self):
        p = Pricing()
        self.assertIsNone(p.price_per_volume_modifier())
        self.assertIsNone(p.price_per_volume_eff())

    def test_price_per_volume_modifier_ignored_if_not_set(self):
        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, None),
            500
        )

    def test_price_per_volume_modifier_not_used(self):
        self.handler.price_per_volume_modifier = 10
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50

        self.assertIsNone(
            p.price_per_volume_modifier()
        )

    def test_price_per_volume_modifier_normal_calc(self):
        self.handler.price_per_volume_modifier = 10
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(
            p.price_per_volume_eff(),
            55
        )

        self.assertEqual(
            p.get_calculated_price(10, None),
            550
        )

    def test_price_per_volume_modifier_normal_calc_2(self):
        self.handler.price_per_volume_modifier = -10
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(
            p.price_per_volume_eff(),
            45
        )

        self.assertEqual(
            p.get_calculated_price(10, None),
            450
        )

    def test_price_per_volume_modifier_price_never_negative(self):
        self.handler.price_per_volume_modifier = -200
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(
            p.price_per_volume_eff(),
            0
        )

    def test_price_per_volume_modifier_no_manager(self):
        p = Pricing(price_base=50000000)
        p.use_price_per_volume_modifier = True
        self.assertIsNone(p.price_per_volume_modifier())

    def test_requires_volume(self):        
        self.assertTrue(Pricing(price_per_volume=10000).requires_volume())
        self.assertTrue(Pricing(volume_min=10000).requires_volume())
        self.assertTrue(Pricing(
            price_per_volume=10000,
            volume_min=10000
        ).requires_volume())
        self.assertFalse(Pricing().requires_volume())

    def test_requires_collateral(self):        
        self.assertTrue(
            Pricing(price_per_collateral_percent=2).requires_collateral()
        )
        self.assertTrue(
            Pricing(collateral_min=50000000).requires_collateral()
        )
        self.assertTrue(
            Pricing(
                price_per_collateral_percent=2,
                collateral_min=50000000
            ).requires_collateral()
        )
        self.assertFalse(Pricing().requires_collateral())

    def test_clean_force_error(self):
        p = Pricing()
        with self.assertRaises(ValidationError):
            p.clean()
    
    def test_is_fix_price(self):
        self.assertTrue(
            Pricing(price_base=50000000).is_fix_price()
        )
        self.assertFalse(
            Pricing(price_base=50000000, price_min=40000000).is_fix_price()
        )
        self.assertFalse(
            Pricing(price_base=50000000, price_per_volume=400).is_fix_price()
        )
        self.assertFalse(
            Pricing(price_base=50000000, price_per_collateral_percent=2)\
                .is_fix_price()
        )
        self.assertFalse(Pricing().is_fix_price())

    def test_clean_normal(self):
        p = Pricing(price_base=50000000)        
        p.clean()



class TestContract(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestContract, cls).setUpClass()
        
        
        

        # Eve characters
        with open(
            currentdir + '/testdata/characters.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.characters_data = json.load(f)

    
    def setUp(self):

        for character in self.characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character['corporation_id'],
                defaults={
                    'corporation_name': character['corporation_name'],
                    'corporation_ticker': character['corporation_ticker'],
                    'member_count': 42
                }
            )
        
        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)
        self.corporation = EveCorporationInfo.objects.get(
            corporation_id=self.character.corporation_id
        )
        
        self.organization = EveEntity.objects.create(
            id = self.character.alliance_id,
            category = EveEntity.CATEGORY_ALLIANCE,
            name = self.character.alliance_name
        )
        
        self.user = User.objects.create_user(
            self.character.character_name,
            'abc@example.com',
            'password'
        )

        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character,
            owner_hash='x1',
            user=self.user
        )        

        # Locations
        self.location_1 = Location.objects.create(
            id=60003760,
            name='Jita IV - Moon 4 - Caldari Navy Assembly Plant',
            solar_system_id=30000142,
            type_id=52678,
            category_id=3
        )
        self.location_2 = Location.objects.create(
            id=1022167642188,
            name='Amamake - 3 Time Nearly AT Winners',
            solar_system_id=30002537,
            type_id=35834,
            category_id=65
        )      

        # create contracts
        self.pricing = Pricing.objects.create(
            start_location=self.location_1,
            end_location=self.location_2,
            price_base=500000000
        )
        
        self.handler = ContractHandler.objects.create(
            organization=self.organization,
            character=self.main_ownership            
        )
        self.contract = Contract.objects.create(
            handler=self.handler,
            contract_id=1,
            collateral=0,
            date_issued=now(),
            date_expired=now() + datetime.timedelta(days=5),
            days_to_complete=3,
            end_location=self.location_2,
            for_corporation=False,
            issuer_corporation=self.corporation,
            issuer=self.character,
            reward=50000000,
            start_location=self.location_1,
            status=Contract.STATUS_OUTSTANDING,
            volume=50000,
            pricing = self.pricing
        )
    

    def test_hours_issued_2_completed(self):
        self.contract.date_completed = \
            self.contract.date_issued + datetime.timedelta(hours=9)

        self.assertEqual(
            self.contract.hours_issued_2_completed,
            9
        )

        self.contract.date_completed = None
        self.assertIsNone(self.contract.hours_issued_2_completed)
            
    
    def test_str(self):
        self.assertEqual(
            str(self.contract),
            '1: Jita -> Amamake'
        )

    def test_date_latest(self):
        # initial contract only had date_issued
        self.assertEqual(
            self.contract.date_issued, 
            self.contract.date_latest
        )

        # adding date_accepted to contract
        self.contract.date_accepted = \
            self.contract.date_issued + datetime.timedelta(days=1)
        self.assertEqual(
            self.contract.date_accepted, 
            self.contract.date_latest
        )

        # adding date_completed to contract
        self.contract.date_completed = \
            self.contract.date_accepted + datetime.timedelta(days=1)
        self.assertEqual(
            self.contract.date_completed, 
            self.contract.date_latest
        )


    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 24)
    def test_has_stale_status(self):
        # initial contract only had date_issued
        # date_issued is now
        self.assertFalse(self.contract.has_stale_status)

        # date_issued is 30 hours ago
        self.contract.date_issued = \
            self.contract.date_issued - datetime.timedelta(hours=30)
        self.assertTrue(self.contract.has_stale_status)


    def test_task_update_pricing(self):
        self.assertTrue(tasks.update_contracts_pricing())


    def test_acceptor_name(self):
        
        contract = self.contract        
        self.assertIsNone(contract.acceptor_name)

        contract.acceptor_corporation = self.corporation
        self.assertEqual(
            contract.acceptor_name,
            self.corporation.corporation_name
        )
        
        contract.acceptor = self.character
        self.assertEqual(
            contract.acceptor_name,
            self.character.character_name
        )


    def test_get_issues_list(self):
        self.assertListEqual(
            self.contract.get_issue_list(),
            []
        )
        self.contract.issues = '["one", "two"]'
        self.assertListEqual(
            self.contract.get_issue_list(),
            ["one", "two"]
        )


    def test_generate_embed_w_pricing(self):
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)
        self.assertEqual(x.color, Contract.EMBED_COLOR_PASSED)


    def test_generate_embed_w_pricing_issues(self):
        self.contract.issues = ['we have issues']
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)
        self.assertEqual(x.color, Contract.EMBED_COLOR_FAILED)


    def test_generate_embed_wo_pricing(self):
        self.contract.pricing = None
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)

    
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_DISABLE_BRANDING', False)
    @patch('freight.models.FREIGHT_DISCORD_MENTIONS', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_pilot_notification_normal(self, mock_webhook_execute):
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)


    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_pilot_notification_no_webhook(self, mock_webhook_execute):
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)


    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_DISABLE_BRANDING', True)    
    @patch('freight.models.Webhook.execute', autospec=True)
    @patch('freight.models.FREIGHT_DISCORD_MENTIONS', None)
    def test_send_pilot_notification_normal(self, mock_webhook_execute):
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)


    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_DISABLE_BRANDING', True)    
    @patch('freight.models.Webhook.execute', autospec=True)
    @patch('freight.models.FREIGHT_DISCORD_MENTIONS', '@here')
    def test_send_pilot_notification_normal(self, mock_webhook_execute):
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)


class TestLocation(TestCase):

    def setUp(self):
        self.location = Location.objects.create(
            id=60003760,
            name='Jita IV - Moon 4 - Caldari Navy Assembly Plant',
            solar_system_id=30000142,
            type_id=52678,
            category_id=3
        )

    def test_str(self):
        self.assertEqual(
            str(self.location.name), 
            'Jita IV - Moon 4 - Caldari Navy Assembly Plant'
        )

    def test_category(self):
        self.assertEqual(self.location.category, Location.CATEGORY_STATION_ID)

    def test_solar_system_name(self):
        self.assertEqual(self.location.solar_system_name, 'Jita')


class TestContractHandler(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestContractHandler, cls).setUpClass()
        
        
        

        # Eve characters
        with open(
            currentdir + '/testdata/characters.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.characters_data = json.load(f)

    
    def setUp(self):
        for character in self.characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character['corporation_id'],
                defaults={
                    'corporation_name': character['corporation_name'],
                    'corporation_ticker': character['corporation_ticker'],
                    'member_count': 42
                }
            )
        
        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)
        self.corporation = EveCorporationInfo.objects.get(
            corporation_id=self.character.corporation_id
        )
        
        self.organization = EveEntity.objects.create(
            id = self.character.alliance_id,
            category = EveEntity.CATEGORY_ALLIANCE,
            name = self.character.alliance_name
        )
        
        self.user = User.objects.create_user(
            self.character.character_name,
            'abc@example.com',
            'password'
        )

        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character,
            owner_hash='x1',
            user=self.user
        )       

        self.handler = ContractHandler.objects.create(
            organization=self.organization,
            character=self.main_ownership            
        )

    def test_str(self):
        self.assertEqual(str(self.handler), 'Justice League')

    
    def test_operation_mode_friendly(self):
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_ALLIANCE
        self.assertEqual(
            self.handler.operation_mode_friendly, 
            'My Alliance'
        )
        self.handler.operation_mode = 'undefined operation mode'
        with self.assertRaises(ValueError):
            self.handler.operation_mode_friendly


    def test_get_availability_text_for_contracts(self):
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_ALLIANCE
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            'Private (Justice League) [My Alliance]'
        )
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_CORPORATION
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            'Private (Justice League) [My Corporation]'
        )
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_PUBLIC
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            'Private (Justice League) '
        )
            
    

        

