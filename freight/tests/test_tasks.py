import datetime
import math
from unittest.mock import Mock, patch

from django.contrib.auth.models import User 
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.authentication.models import CharacterOwnership
from esi.models import Token
from esi.errors import TokenExpiredError, TokenInvalidError

from . import TempDisconnectPricingSaveHandler
from .. import tasks
from ..app_settings import (
    FREIGHT_OPERATION_MODE_MY_CORPORATION, 
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_CORP_PUBLIC,
    FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
    FREIGHT_OPERATION_MODES
)
from .auth_utils_2 import AuthUtils2
from ..models import Contract, ContractHandler, EveEntity, Location, Pricing
from .testdata import (
    contracts_data,
    create_locations,
    create_contract_handler_w_contracts, 
    create_entities_from_characters
)
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'freight.tasks'
logger = set_test_logger(MODULE_PATH, __file__)


class TestContractsSync(NoSocketsTestCase):
    
    def setUp(self):

        create_entities_from_characters()
        
        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)
        
        self.alliance = EveEntity.objects.get(
            id=self.character.alliance_id
        )
        self.corporation = EveEntity.objects.get(
            id=self.character.corporation_id
        )
        self.user = User.objects.create_user(
            self.character.character_name,
            'abc@example.com', 'password'
        )

        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character,
            owner_hash='x1',
            user=self.user
        )        

        create_locations()
        
    # identify wrong operation mode
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.Token')    
    def test_run_manager_sync_expired_token(self, mock_Token):        
        mock_Token.objects.filter.side_effect = TokenExpiredError()        
        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.Token')
    def test_run_manager_sync_invalid_token(self, mock_Token):
        mock_Token.objects.filter.side_effect = TokenInvalidError()
        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.Token')    
    def test_run_manager_sync_no_valid_token(
        self,             
        mock_Token
    ):        
        mock_Token.objects.filter.return_value.require_scopes.return_value\
            .require_valid.return_value.first.return_value = None
        
        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )        
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(
        MODULE_PATH + '.Contract.objects.update_or_create_from_dict'
    )
    @patch(MODULE_PATH + '.Token')
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
                len(contracts_data) / page_size
            ))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]

        def func_Contracts_objects_update_or_create_from_dict(
            handler, 
            contract, 
            esi_client
        ):            
            raise RuntimeError('Test exception')
            
        mock_Contracts_objects_update_or_create_from_dict\
            .side_effect = func_Contracts_objects_update_or_create_from_dict

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

        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.Token')
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]

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

        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects
            .filter(status__exact=Contract.STATUS_OUTSTANDING)
            .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [149409005, 149409014, 149409006, 149409015]
        )

    # normal synch of new contracts, mode my_corporation
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE',
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch(MODULE_PATH + '.Token')
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]
        
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

        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        self.assertEqual(mock_operation.result.call_count, 9)
        
        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects
            .filter(status__exact=Contract.STATUS_OUTSTANDING)
            .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [
                149409016, 
                149409061, 
                149409062,
                149409063, 
                149409064, 
            ]
        )

    # normal synch of new contracts, mode my_corporation
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
    )
    @patch(MODULE_PATH + '.Token')
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]
        
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

        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects
            .filter(status__exact=Contract.STATUS_OUTSTANDING)
            .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [
                149409016, 
                149409017, 
                149409061, 
                149409062,
                149409063, 
                149409064, 
            ]
        )

    # normal synch of new contracts, mode corp_public
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_CORP_PUBLIC
    )    
    @patch(MODULE_PATH + '.Token')
    @patch(
        'freight.managers.EveCorporationInfo.objects.create_corporation', 
        side_effect=ObjectNotFound(9999999, 'corporation')
    )
    @patch(
        'freight.managers.EveCharacter.objects.create_character', 
        side_effect=ObjectNotFound(9999999, 'character')
    )
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]
        
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

        AuthUtils2.add_permission_to_user_by_name(
            'freight.setup_contract_handler', self.user
        )
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
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x['contract_id'] 
            for x in Contract.objects
            .filter(status__exact=Contract.STATUS_OUTSTANDING)
            .values('contract_id')
        ]
        self.assertCountEqual(
            contract_ids,
            [
                149409016, 
                149409061, 
                149409062, 
                149409063, 
                149409064, 
                149409017, 
                149409018
            ]
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
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
    )
    @patch(MODULE_PATH + '.send_contract_notifications')
    @patch(MODULE_PATH + '.esi_client_factory')
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
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            if mock_calls_count == 1:
                mock_response = Mock()
                mock_response.headers = {'x-pages': pages_count}
                return [contracts_data[start:stop], mock_response]
            else:
                return contracts_data[start:stop]
        
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


class TestNotifications(NoSocketsTestCase):
          
    def setUp(self):

        create_contract_handler_w_contracts()
        
        # disable pricing signal                
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)        
        with TempDisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )
                
        Contract.objects.update_pricing() 

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_pilot_notifications_normal(self, mock_webhook_execute):        
        logger.debug('test_send_pilot_notifications_normal - start')
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 8)
        logger.debug('test_send_pilot_notifications_normal - complete')

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_customer_notifications_normal(self, mock_webhook_execute):        
        logger.debug('test_send_customer_notifications_normal - start')
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 12)
        logger.debug('test_send_customer_notifications_normal - complete')

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_pilot_notifications_for_expired_contracts(
        self, mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_customer_notifications_for_expired_contracts(
        self, mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
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

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')    
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_send_customer_notifications_only_once_per_state(
        self, mock_webhook_execute
    ):        
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()        
        
        # round #1
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.Webhook.execute', autospec=True)
    def test_dont_send_any_notifications_when_no_url_if_set(
        self, mock_webhook_execute
    ):                
        self.assertTrue(tasks.send_contract_notifications(rate_limted=False))
        self.assertEqual(mock_webhook_execute.call_count, 0)
