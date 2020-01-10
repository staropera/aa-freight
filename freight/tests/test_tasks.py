import datetime
import inspect
import json
import math
import os
from random import randrange
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.authentication.models import CharacterOwnership
from allianceauth.services.modules.discord.models import DiscordUser
from esi.models import Token
from esi.errors import TokenExpiredError, TokenInvalidError

from . import _set_logger
from .. import tasks
from ..app_settings import *
from ..models import *


logger = _set_logger('freight.tasks', __file__)

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))


class TestContractsSync(TestCase):
   
    @classmethod
    def setUpClass(cls):
        super(TestContractsSync, cls).setUpClass()

        print()
        print('Running tests for class: {}'.format(cls))

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
        self.character = EveCharacter.objects.get(character_id=90000001)
        
        self.alliance = EveEntity.objects.get(
            id = self.character.alliance_id
        )
        self.corporation = EveEntity.objects.get(
            id = self.character.corporation_id
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

    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.tasks.Token')    
    def test_run_manager_sync_no_valid_token(
            self,             
            mock_Token
        ):                
        
        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = None
                        
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

    # exception occuring for one of the contracts    
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(
        'freight.tasks.Contract.objects.update_or_create_from_dict'
    )
    @patch('freight.tasks.Token')
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_contract_fails(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications,
            mock_Token,
            mock_Contracts_objects_update_or_create_from_dict
        ):
        
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(
                len(self.contracts) / page_size
            ))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [self.contracts[start:stop], mock_response]
            else:
                return self.contracts[start:stop]

        def func_Contracts_objects_update_or_create_from_dict(
            handler, 
            contract, 
            esi_client
        ):            
            raise RuntimeError('Test exception')
            

        mock_Contracts_objects_update_or_create_from_dict\
            .side_effect = \
                func_Contracts_objects_update_or_create_from_dict

        mock_client = Mock()
        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page        
        mock_client.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )
        mock_esi_client_factory.return_value = mock_client        
        mock_send_contract_notifications.delay = Mock()        

        mock_Token.objects.filter.return_value\
            .require_scopes.return_value\
            .require_valid.return_value\
            .first.return_value = Mock(spec=Token)

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
            ContractHandler.ERROR_UNKNOWN            
        )
        

    # normal synch of new contracts, mode my_alliance
    # freight.tests.TestRunContractsSync.test_run_manager_sync_normal_my_alliance    
    @patch(
        'freight.tasks.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.tasks.Token')
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_my_alliance_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications,
            mock_Token
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

        mock_Token.objects.filter.return_value\
            .require_scopes.return_value\
            .require_valid.return_value\
            .first.return_value = Mock(spec=Token)

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
    @patch('freight.tasks.Token')
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_my_corporation_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications,
            mock_Token
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

        mock_Token.objects.filter.return_value\
            .require_scopes.return_value\
            .require_valid.return_value\
            .first.return_value = Mock(spec=Token)

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
    @patch('freight.tasks.Token')
    @patch('freight.tasks.send_contract_notifications')
    @patch('freight.tasks.esi_client_factory')
    def test_sync_corp_in_alliance_contracts_only(
            self, 
            mock_esi_client_factory, 
            mock_send_contract_notifications,
            mock_Token
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

        mock_Token.objects.filter.return_value\
            .require_scopes.return_value\
            .require_valid.return_value\
            .first.return_value = Mock(spec=Token)    

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
    @patch('freight.tasks.Token')
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
            mock_EveCorporationInfo_objects_create_corporation,
            mock_Token
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

        mock_Token.objects.filter.return_value\
            .require_scopes.return_value\
            .require_valid.return_value\
            .first.return_value = Mock(spec=Token)  

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


class TestNotifications(TestCase):
        
    @classmethod
    def setUpClass(cls):
        print()
        print('Running tests for class: {}'.format(cls))

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
        self.character = EveCharacter.objects.get(character_id=90000001)
        
        self.organization = EveEntity.objects.get(
            id = self.character.alliance_id
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
            if contract['type'] == 'courier':
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

    