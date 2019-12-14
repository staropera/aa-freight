import datetime
import logging
import inspect
import json
import math
import os
from random import randrange
import sys
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.authentication.models import CharacterOwnership
from allianceauth.services.modules.discord.models import DiscordUser
from esi.models import Token, Scope
from esi.errors import TokenExpiredError, TokenInvalidError

from . import tasks
from .app_settings import *
from .models import *
from .templatetags.freight_filters import power10, formatnumber
from . import views


# reconfigure logger so we get logging from tasks to console during test
c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
c_handler = logging.StreamHandler(sys.stdout)
c_handler.setFormatter(c_format)
logger = logging.getLogger('freight.tasks')
logger.level = logging.DEBUG
logger.addHandler(c_handler)


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
        
        alliance = EveOrganization.objects.create(
            id = character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
            name = character.alliance_name
        )
        
        self.handler = ContractHandler.objects.create(
            organization=alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE
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
        p.price_base = 500        
        self.assertIsNone(p.get_contract_price_check_issues(5, 10))
        
        p = Pricing()
        p.price_base = 500
        p.volume_max = 300        
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 1000))

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



class TestContractsSync(TestCase):
   
    @classmethod
    def setUpClass(cls):
        super(TestContractsSync, cls).setUpClass()

        # ESI contracts        
        with open(
            currentdir + '/testdata/contracts.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.contracts = json.load(f)

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
        
        self.alliance = EveOrganization.objects.create(
            id = self.character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
            name = self.character.alliance_name
        )
        self.corporation = EveOrganization.objects.create(
            id = self.character.corporation_id,
            category = EveOrganization.CATEGORY_CORPORATION,
            name = self.character.corporation_name
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
        Location.objects.create(
            id=60003760,
            name='Jita IV - Moon 4 - Caldari Navy Assembly Plant',
            solar_system_id=30000142,
            type_id=52678,
            category_id=3
        )
        Location.objects.create(
            id=1022167642188,
            name='Amamake - 3 Time Nearly AT Winners',
            solar_system_id=30002537,
            type_id=35834,
            category_id=65
        )      
        

    # identify wrong operation mode
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    def test_run_wrong_operation_mode(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
        )
        self.assertFalse(
            tasks.run_contracts_sync()
        )
        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_OPERATION_MODE_MISMATCH
        )


    # run without char    
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    def test_run_no_sync_char(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,            
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        self.assertFalse(
            tasks.run_contracts_sync()
        )
        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NO_CHARACTER
        )

    
    # test expired token
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.tasks.Token')    
    def test_run_manager_sync_expired_token(
            self,             
            mock_Token
        ):                
        
        mock_Token.objects.filter.side_effect = TokenExpiredError()        
                        
        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        
        # run manager sync
        self.assertFalse(tasks.run_contracts_sync())

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_TOKEN_EXPIRED            
        )

    
    # test invalid token
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.tasks.Token')
    def test_run_manager_sync_invalid_token(
            self,             
            mock_Token
        ):                
        
        mock_Token.objects.filter.side_effect = TokenInvalidError()        
                        
        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        
        # run manager sync
        self.assertFalse(tasks.run_contracts_sync())

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_TOKEN_INVALID            
        )


    # normal synch of new contracts, mode my_alliance
    # freight.tests.TestRunContractsSync.test_run_manager_sync_normal_my_alliance    
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_my_alliance_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications            
        ):
        
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(self.contracts) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]

        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE
        )
        
        # run manager sync
        self.assertTrue(
            tasks.run_contracts_sync()
        )

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NONE            
        )
        
        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 7)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects\
                .filter(status__exact=Contract.STATUS_OUTSTANDING)\
                .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409005, 149409014, 149409006, 149409015]
        )

    # normal synch of new contracts, mode my_corporation
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE',
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_my_corporation_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications
        ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(self.contracts) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]
        
        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_CORPORATION
        )
        
        # run manager sync
        self.assertTrue(
            tasks.run_contracts_sync()
        )

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NONE            
        )
        
        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 7)
        
        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects\
                .filter(status__exact=Contract.STATUS_OUTSTANDING)\
                .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409016]
        )

    # normal synch of new contracts, mode my_corporation
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
    )
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_corp_in_alliance_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications
        ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(self.contracts) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]
        
        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
        )
        
        # run manager sync
        self.assertTrue(
            tasks.run_contracts_sync()
        )

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NONE            
        )
        
        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 7)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects\
                .filter(status__exact=Contract.STATUS_OUTSTANDING)\
                .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409016, 149409017]
        )

    # normal synch of new contracts, mode corp_public
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_CORP_PUBLIC
    )    
    @patch(
        'freight.managers.EveCorporationInfo.objects.create_corporation', 
        side_effect=ObjectNotFound(9999999, 'corporation')
    )
    @patch(
        'freight.managers.EveCharacter.objects.create_character', 
        side_effect=ObjectNotFound(9999999, 'character')
    )
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_corp_public_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications,
            mock_EveCharacter_objects_create_character,
            mock_EveCorporationInfo_objects_create_corporation
        ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(self.contracts) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]
        
        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        # create test data
        p = Permission.objects.filter(            
            codename='setup_contract_handler'
        ).first()
        self.user.user_permissions.add(p)
        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_CORP_PUBLIC
        )
        
        # run manager sync
        self.assertTrue(
            tasks.run_contracts_sync()
        )

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NONE            
        )
        
        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 7)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects\
                .filter(status__exact=Contract.STATUS_OUTSTANDING)\
                .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409016, 149409017, 149409018]
        )
        
    def test_operation_mode_friendly(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
        )
        self.assertEqual(
            handler.operation_mode_friendly,
            FREIGHT_OPERATION_MODES[0][1]
        )

        handler.operation_mode = FREIGHT_OPERATION_MODE_MY_CORPORATION
        self.assertEqual(
            handler.operation_mode_friendly,
            FREIGHT_OPERATION_MODES[1][1]
        )

        handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
        self.assertEqual(
            handler.operation_mode_friendly,
            FREIGHT_OPERATION_MODES[2][1]
        )

        handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_PUBLIC
        self.assertEqual(
            handler.operation_mode_friendly,
            FREIGHT_OPERATION_MODES[3][1]
        )

    def test_last_error_message_friendly(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
            last_error=ContractHandler.ERROR_UNKNOWN
        )
        self.assertEqual(
            handler.last_error_message_friendly,
            ContractHandler.ERRORS_LIST[7][1]
        )

    """
    # freight.tests.TestRunContractsSync.test_statistics_calculation
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE)
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_statistics_calculation(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications
        ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            #returns single page for operation.result(), first with header
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(self.contracts) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]
        
        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        # create test data
        p = Permission.objects.filter(codename='basic_access').first()
        self.user.user_permissions.add(p)
        p = Permission.objects.filter(codename='setup_contract_handler').first()
        self.user.user_permissions.add(p)
        p = Permission.objects.filter(codename='view_contract').first()
        self.user.user_permissions.add(p)

        self.user.save()
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
        )
        
        # run manager sync
        self.assertTrue(
            tasks.run_contracts_sync()
        )

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_NONE            
        )
        
        result = self.client.login(
            username=self.character.character_name, 
            password='password'
        )

        response = self.client.get(reverse('freight:index'))
        
        print('hi')
    """


class TestFilters(TestCase):

    def test_power10(self):
        self.assertEqual(
            power10(1),
            1
        )
        self.assertEqual(
            power10(1000, 3),
            1
        )
        self.assertEqual(
            power10(-1000, 3),
            -1
        )
        self.assertEqual(
            power10(0),
            0            
        )
        self.assertEqual(
            power10(None, 3),
            None
        )
        self.assertEqual(
            power10('xxx', 3),
            None
        )
        self.assertEqual(
            power10('', 3),
            None
        )
        self.assertEqual(
            power10(1000, 'xx'),
            None
        )

    def test_formatnumber(self):
        self.assertEqual(
            formatnumber(1),
            '1.0'
        )
        self.assertEqual(
            formatnumber(1000),
            '1,000.0'
        )
        self.assertEqual(
            formatnumber(1000000),
            '1,000,000.0'
        )
        self.assertEqual(
            formatnumber(1, 0),
            '1'
        )
        self.assertEqual(
            formatnumber(1000, 0),
            '1,000'
        )
        self.assertEqual(
            formatnumber(1000000, 0),
            '1,000,000'
        )
        self.assertEqual(
            formatnumber(-1000),
            '-1,000.0'
        )
        self.assertEqual(
            formatnumber(None),
            None
        )


class TestNotifications(TestCase):
        
    @classmethod
    def setUpClass(cls):
        super(TestNotifications, cls).setUpClass()

        # ESI contracts        
        with open(
            currentdir + '/testdata/contracts.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.contracts = json.load(f)
                
        # update dates to something current, so won't be treated as stale
        for contract in cls.contracts:
            date_issued = now() - datetime.timedelta(
                days=randrange(1), 
                hours=randrange(10)
            )
            date_accepted = date_issued + datetime.timedelta(
                hours=randrange(5),
                minutes=randrange(30)
            )
            date_completed = date_accepted + datetime.timedelta(
                hours=randrange(12),
                minutes=randrange(30)
            )
            date_expired = now() + datetime.timedelta(
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
        
        self.organization = EveOrganization.objects.create(
            id = self.character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
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

        # create contracts
        pricing = Pricing.objects.create(
            start_location=jita,
            end_location=amamake,
            price_base=500000000
        )
        
        handler = ContractHandler.objects.create(
            organization=self.organization,
            character=self.main_ownership            
        )
        
        for contract in self.contracts:
            Contract.objects.update_or_create_from_dict(
                handler=handler,
                contract=contract,
                esi_client=Mock()
            )

        Contract.objects.update_pricing() 

        # create users and Discord accounts from contract issuers
        for contract in Contract.objects.all():
            issuer_user = User.objects\
                .filter(
                    character_ownerships__character__exact=contract.issuer
                )\
                .first()
            if not issuer_user:
                user = User.objects.create_user(
                    contract.issuer.character_name,
                    'abc@example.com',
                    'password'
                )
                CharacterOwnership.objects.create(
                    character=contract.issuer,
                    owner_hash=contract.issuer.character_name + 'x',
                    user=user
                )   
            DiscordUser.objects.update_or_create(
                user=user,
                defaults={
                    "uid": contract.issuer.character_id
                }
            )


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_pilot_notifications_normal(
        self, 
        mock_webhook_execute
    ):        
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 7)


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_customer_notifications_normal(
        self, 
        mock_webhook_execute
    ):        
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 10)

    
    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_pilot_notifications_for_expired_contracts(
        self, 
        mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_customer_notifications_for_expired_contracts(
        self, 
        mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_pilot_notifications_only_once(
        self, 
        mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()        
        
        # round #1
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_customer_notifications_only_once_per_state(
        self, 
        mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()        
        
        # round #1
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)


    @patch('freight.managers.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_any_notifications_when_no_url_if_set(
        self, 
        mock_webhook_execute
    ):                
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)

    

class TestViews(TestCase):
    
    # note: setup is making calls to ESI to get full info for entities
    # all ESI calls in the tested module are mocked though


    @classmethod
    def setUpClass(cls):
        super(TestViews, cls).setUpClass()

        # ESI contracts        
        with open(
            currentdir + '/testdata/contracts.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.contracts = json.load(f)
                
        # update dates to something current, so won't be treated as stale
        for contract in cls.contracts:
            date_issued = now() - datetime.timedelta(
                days=randrange(5), 
                hours=randrange(10)
            )
            date_accepted = date_issued + datetime.timedelta(
                hours=randrange(5),
                minutes=randrange(30)
            )
            date_completed = date_accepted + datetime.timedelta(
                hours=randrange(12),
                minutes=randrange(30)
            )
            date_expired = now() + datetime.timedelta(
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
        
        self.factory = RequestFactory()

        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)
        
        self.organization = EveOrganization.objects.create(
            id = self.character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
            name = self.character.alliance_name
        )
        
        self.user = User.objects.create_user(
            self.character.character_name,
            'abc@example.com',
            'password'
        )

        # user needs basic permission to access the app
        p = Permission.objects.get(
            codename='basic_access', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character,
            owner_hash='x1',
            user=self.user
        )        

        # Locations
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

        # create contracts
        self.pricing = Pricing.objects.create(
            start_location=jita,
            end_location=amamake,
            price_base=500000000
        )
        
        self.handler = ContractHandler.objects.create(
            organization=self.organization,
            character=self.main_ownership            
        )
        
        for contract in self.contracts:
            Contract.objects.update_or_create_from_dict(
                handler=self.handler,
                contract=contract,
                esi_client=Mock()
            )

        Contract.objects.update_pricing() 

        # create users and Discord accounts from contract issuers
        for contract in Contract.objects.all():
            issuer_user = User.objects\
                .filter(
                    character_ownerships__character__exact=contract.issuer
                )\
                .first()
            if not issuer_user:
                user = User.objects.create_user(
                    contract.issuer.character_name,
                    'abc@example.com',
                    'password'
                )
                CharacterOwnership.objects.create(
                    character=contract.issuer,
                    owner_hash=contract.issuer.character_name + 'x',
                    user=user
                )   
            DiscordUser.objects.update_or_create(
                user=user,
                defaults={
                    "uid": contract.issuer.character_id
                }
            )


    def test_calculator_access_with_permission(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()
        
        request = self.factory.get(reverse('freight:calculator'))
        request.user = self.user
        response = views.calculator(request)
        self.assertEqual(response.status_code, 200)


    def test_calculator_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:calculator'))
        request.user = self.user
        response = views.calculator(request)
        self.assertNotEqual(response.status_code, 200)


    def test_calculator_perform_calculation(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()
        
        data = {
            'pricing': self.pricing.pk,
            'volume': 0,
            'collateral': 0
        }
        url = reverse('freight:calculator', args={self.pricing.pk})
        request = self.factory.post(url, data)
        request.user = self.user        
        response = views.calculator(request, self.pricing.pk)
        self.assertEqual(response.status_code, 200)


    def test_contract_list_active_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user
        response = views.contract_list_active(request)
        self.assertNotEqual(response.status_code, 200)


    def test_contract_list_active_access_with_permission(self):
        p = Permission.objects.get(
            codename='view_contracts', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user
        
        response = views.contract_list_active(request)
        self.assertEqual(response.status_code, 200)
    
    """
    def test_contract_list_data_activate(self):
        p = Permission.objects.get(
            codename='view_contracts', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_ACTIVE}
        ))
        request.user = self.user
        
        response = views.contract_list_data(
            request, 
            views.CONTRACT_LIST_ACTIVE
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = { x['contract_id'] for x in data }
        self.assertSetEqual(
            contract_ids, 
            {
                149409005,
                149409014,
                149409006,
                149409015,
                149409016,
                149409017,
                149409018,
                149409019
            }
        )

    """


    def test_contract_list_user_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user
        response = views.contract_list_user(request)
        self.assertNotEqual(response.status_code, 200)


    def test_contract_list_user_access_with_permission(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user
        
        response = views.contract_list_user(request)
        self.assertEqual(response.status_code, 200)

    def test_contract_list_data_user_no_access_without_permission(self):
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_USER}
        ))
        request.user = self.user
        
        with self.assertRaises(RuntimeError):
            response = views.contract_list_data(
                request, 
                views.CONTRACT_LIST_USER
            )
        

    def test_contract_list_data_user(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_USER}
        ))
        request.user = self.user
        
        response = views.contract_list_data(
            request, 
            views.CONTRACT_LIST_USER
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = { x['contract_id'] for x in data }
        self.assertSetEqual(
            contract_ids, 
            {
                149409016,
                149419318,              
            }
        )
    
    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch('freight.views.tasks.run_contracts_sync.delay', autospec=True)
    def test_setup_contract_handler(
        self,         
        mock_run_contracts_sync,
        mock_message_plus
    ):
        p = Permission.objects.get(
            codename='setup_contract_handler', 
            content_type__app_label=__package__
        )
        self.user.user_permissions.add(p)
        self.user.save()

        ContractHandler.objects.all().delete()

        token = Mock(spec=Token)
        token.character_id = self.character.character_id
        request = self.factory.post(
            reverse('freight:setup_contract_handler'),
            data={
                '_token': 1
            }
        )
        request.user = self.user
        request.token = token
        request.token_char = self.character

        orig_view  = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)
        self.assertEqual(mock_run_contracts_sync.call_count, 1)


class TestModelContract(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestModelContract, cls).setUpClass()
        
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
        
        self.organization = EveOrganization.objects.create(
            id = self.character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
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
            volume=50000
        )
    
    def test_hours_issued_2_completed(self):
        self.contract.date_completed = \
            self.contract.date_issued + datetime.timedelta(hours=9)

        self.assertEqual(
            self.contract.hours_issued_2_completed,
            9
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