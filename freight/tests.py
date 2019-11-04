import logging
import inspect
import json
import math
import os
import sys
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.authentication.models import CharacterOwnership
from esi.models import Token, Scope
from esi.errors import TokenExpiredError, TokenInvalidError

from . import tasks
from .app_settings import *
from .models import *
from .templatetags.freight_filters import power10, formatnumber


# reconfigure logger so we get logging from tasks to console during test
c_handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger('freight.tasks')
logger.level = logging.DEBUG
logger.addHandler(c_handler)


class TestPricing(TestCase):

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
        

class TestRunContractsSync(TestCase):
    
    # note: setup is making calls to ESI to get full info for entities
    # all ESI calls in the tested module are mocked though


    @classmethod
    def setUpClass(cls):
        super(TestRunContractsSync, cls).setUpClass()

        # load test data
        currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
            inspect.currentframe()
        )))

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
            characters = json.load(f)

        for character in characters:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character['corporation_id'],
                defaults={
                    'corporation_name': character['corporation_name'],
                    'corporation_ticker': character['corporation_ticker'],
                    'member_count': 42
                }
            )

        # setup test data
        # 1 user
        cls.character = EveCharacter.objects.get(character_id=90000001)
        
        cls.alliance = EveOrganization.objects.create(
            id = cls.character.alliance_id,
            category = EveOrganization.CATEGORY_ALLIANCE,
            name = cls.character.alliance_name
        )
        cls.corporation = EveOrganization.objects.create(
            id = cls.character.corporation_id,
            category = EveOrganization.CATEGORY_CORPORATION,
            name = cls.character.corporation_name
        )
        cls.user = User.objects.create_user(cls.character.character_name)

        cls.main_ownership = CharacterOwnership.objects.create(
            character=cls.character,
            owner_hash='x1',
            user=cls.user
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
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_MY_CORPORATION)
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
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_MY_ALLIANCE)
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
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_MY_ALLIANCE)
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
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_MY_ALLIANCE)
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
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_MY_ALLIANCE)
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
        self.assertEqual(mock_operation.result.call_count, 4)

        # should only contain the right contract
        self.assertCountEqual(
            [x['contract_id'] for x in Contract.objects.values('contract_id')],
            [149409005, 149409014, 149409006, 149409015]
        )

    # normal synch of new contracts, mode my_corporation
    @patch('freight.tasks.FREIGHT_OPERATION_MODE',FREIGHT_OPERATION_MODE_MY_CORPORATION)
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
        self.assertEqual(mock_operation.result.call_count, 4)

        # should only contain the right contract
        self.assertCountEqual(
            [x['contract_id'] for x in Contract.objects.values('contract_id')],
            [149409016]
        )

    # normal synch of new contracts, mode my_corporation
    @patch('freight.tasks.FREIGHT_OPERATION_MODE', FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE)
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
        self.assertEqual(mock_operation.result.call_count, 4)

        # should only contain the right contract
        contract_ids = [
            x['contract_id'] for x in Contract.objects.values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409016, 149409017]
        )


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