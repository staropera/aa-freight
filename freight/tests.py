import logging
import inspect
import json
import math
import os
import sys
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase

from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo
from allianceauth.authentication.models import CharacterOwnership
from esi.models import Token, Scope
from esi.errors import TokenExpiredError, TokenInvalidError

from . import tasks
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
        with self.assertRaises(ValidationError):
            p.get_calculated_price(1, 1)

    
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
        
        p = Pricing()
        with self.assertRaises(ValidationError):
            p.get_calculated_price(1, 1)


class TestRunContractsSync(TestCase):
    
    # note: setup is making calls to ESI to get full info for entities
    # all ESI calls in the tested module are mocked though


    @classmethod
    def setUpClass(cls):
        super(TestRunContractsSync, cls).setUpClass()

        # create environment
        # 1 user
        cls.character = EveCharacter.objects.create_character(207150426)  
        cls.alliance_id = 498125261        
        cls.alliance = EveAllianceInfo.objects.create_alliance(
            cls.alliance_id
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
        
        # ESI contracts
        currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
            inspect.currentframe()
        )))
        with open(
            currentdir + '/testdata/contracts.json', 
            'r', 
            encoding='utf-8'
        ) as f:
            cls.contracts = json.load(f)


    # normal synch of new contracts
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_run_manager_sync_normal(
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
            alliance=self.alliance,
            character=self.main_ownership
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
        self.assertEqual(mock_operation.result.call_count, 3)

        # should be number of contracts stored in DV        
        self.assertEqual(
            Contract.objects.filter(handler=handler).count(),
            4
        )

        
    # run without char    
    def test_run_no_sync_char(self):
        handler = ContractHandler.objects.create(
            alliance=self.alliance
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
            alliance=self.alliance,
            character=self.main_ownership
        )
        
        # run manager sync
        self.assertFalse(tasks.run_contracts_sync())

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_TOKEN_EXPIRED            
        )

    
    # test invalid token
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
            alliance=self.alliance,
            character=self.main_ownership
        )
        
        # run manager sync
        self.assertFalse(tasks.run_contracts_sync())

        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, 
            ContractHandler.ERROR_TOKEN_INVALID            
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