import datetime
import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.urls import reverse
from django.utils.timezone import now


from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.authentication.models import CharacterOwnership
from esi.models import Token

from . import set_logger, TempDisconnectPricingSaveHandler, generate_token,\
    store_as_Token
from ..app_settings import *
from ..forms import AddLocationForm
from ..models import *
from .. import views
from .testdata import contracts_data, create_contract_handler_w_contracts


logger = set_logger('freight.views', __file__)

HTTP_OK = 200
HTTP_REDIRECT = 302


class TestCalculator(TestCase):
    
    def setUp(self):
        self.user = create_contract_handler_w_contracts()
        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            self.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        self.factory = RequestFactory()


    def test_index(self):        
        request = self.factory.get(reverse('freight:index'))
        request.user = self.user
        response = views.index(request)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:calculator'))


    def test_calculator_access_with_permission(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()
        
        request = self.factory.get(reverse('freight:calculator'))
        request.user = self.user
        response = views.calculator(request)
        self.assertEqual(response.status_code, HTTP_OK)


    def test_calculator_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:calculator'))
        request.user = self.user
        response = views.calculator(request)
        self.assertNotEqual(response.status_code, HTTP_OK)


    def test_calculator_perform_calculation(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, HTTP_OK)


class TestContractList(TestCase):
    
    def setUp(self):
        self.user = create_contract_handler_w_contracts()

        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            self.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        self.factory = RequestFactory()


    def test_active_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user
        response = views.contract_list_active(request)
        self.assertNotEqual(response.status_code, HTTP_OK)


    def test_active_access_with_permission(self):
        p = Permission.objects.get(
            codename='view_contracts', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user
        
        response = views.contract_list_active(request)
        self.assertEqual(response.status_code, HTTP_OK)
    

    def test_data_activate(self):
        p = Permission.objects.get(
            codename='view_contracts', 
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, HTTP_OK)

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
                149409064,
                149409061,
                149409062,
                149409063,
                149409017,
                149409018,
                149409019
            }
        )


    def test_data_invalid_category(self):
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={'this_is_not_valid'}
        ))
        request.user = self.user
        
        with self.assertRaises(ValueError):
            views.contract_list_data(
                request, 
                'this_is_not_valid'
            )
        

    def test_user_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user
        response = views.contract_list_user(request)
        self.assertNotEqual(response.status_code, HTTP_OK)


    def test_user_access_with_permission(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user
        
        response = views.contract_list_user(request)
        self.assertEqual(response.status_code, HTTP_OK)


    def test_data_user_no_access_without_permission_1(self):
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

    def test_data_user_no_access_without_permission_2(self):
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_ACTIVE}
        ))
        request.user = self.user
        
        with self.assertRaises(RuntimeError):
            response = views.contract_list_data(
                request, 
                views.CONTRACT_LIST_ACTIVE
            )
        

    def test_data_user(self):
        p = Permission.objects.get(
            codename='use_calculator', 
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = { x['contract_id'] for x in data }
        self.assertSetEqual(
            contract_ids, 
            {
                149409016,
                149409061,
                149409062,
                149409063,
                149409064,
            }
        )


class TestSetupContractHandler(TestCase):

    def setUp(self):
        self.user = create_contract_handler_w_contracts([])
        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            self.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        self.factory = RequestFactory()
    
    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch('freight.views.tasks.run_contracts_sync', autospec=True)
    def test_normal(
        self,         
        mock_run_contracts_sync,
        mock_message_plus
    ):
        p = Permission.objects.get(
            codename='setup_contract_handler', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        ContractHandler.objects.all().delete()

        token = Mock(spec=Token)
        token.character_id = self.user.profile.main_character.character_id
        request = self.factory.post(
            reverse('freight:setup_contract_handler'),
            data={
                '_token': 1
            }
        )
        request.user = self.user
        request.token = token
        
        orig_view  = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)
        self.assertEqual(mock_run_contracts_sync.delay.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))


    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch('freight.views.tasks.run_contracts_sync', autospec=True)
    def test_error_no_alliance_member(
        self,         
        mock_run_contracts_sync,
        mock_message_plus
    ):
        p = Permission.objects.get(
            codename='setup_contract_handler', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        ContractHandler.objects.all().delete()
        
        token = Mock(spec=Token)
        token_char = EveCharacter.objects.get(character_id=90000005)        
        token.character_id = token_char.character_id
        request = self.factory.post(
            reverse('freight:setup_contract_handler'),
            data={
                '_token': 1
            }
        )
        request.user = self.user
        request.token = token
        
        orig_view  = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))


    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch('freight.views.tasks.run_contracts_sync', autospec=True)
    def test_error_character_not_owned(
        self,         
        mock_run_contracts_sync,
        mock_message_plus
    ):
        p = Permission.objects.get(
            codename='setup_contract_handler', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        ContractHandler.objects.all().delete()

        token = Mock(spec=Token)
        token_char = EveCharacter.objects.get(character_id=90000005)        
        token.character_id = token_char.character_id
        request = self.factory.post(
            reverse('freight:setup_contract_handler'),
            data={
                '_token': 1
            }
        )
        request.user = self.user
        request.token = token
        
        orig_view  = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))


    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch('freight.views.tasks.run_contracts_sync', autospec=True)
    def test_error_wrong_operation_mode(
        self,         
        mock_run_contracts_sync,
        mock_message_plus
    ):
        p = Permission.objects.get(
            codename='setup_contract_handler', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()
        
        token = Mock(spec=Token)
        token.character_id = self.user.profile.main_character.character_id
        request = self.factory.post(
            reverse('freight:setup_contract_handler'),
            data={
                '_token': 1
            }
        )
        request.user = self.user
        request.token = token
        
        orig_view  = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))
    

class TestStatistics(TestCase):

    def setUp(self):
        self.user = create_contract_handler_w_contracts()
        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            self.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        self.factory = RequestFactory()


    def test_statistics_routes_data(self):
        p = Permission.objects.get(
            codename='view_statistics', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:statistics_routes_data'
        ))
        request.user = self.user
        
        response = views.statistics_routes_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{
                'contracts': '3', 
                'collaterals': '3,000', 
                'pilots': '1', 
                'name': 'Jita <-> Amamake', 
                'customers': '1', 
                'rewards': '300'
            }]
        )

    def test_statistics_pilots_data(self):
        p = Permission.objects.get(
            codename='view_statistics', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:statistics_pilots_data'
        ))
        request.user = self.user
        
        response = views.statistics_pilots_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{'collaterals': '3,000', 'rewards': '300', 'corporation': 'Wayne Enterprise', 'contracts': '3', 'name': 'Bruce Wayne'}]
        )


    def test_statistics_pilot_corporations_data(self):
        p = Permission.objects.get(
            codename='view_statistics', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:statistics_pilot_corporations_data'
        ))
        request.user = self.user
        
        response = views.statistics_pilot_corporations_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{
                'name': 'Wayne Enterprise', 
                'rewards': '300', 
                'alliance': '', 
                'collaterals': '3,000', 
                'contracts': '3'
            }]
        )


    def test_statistics_customer_data(self):
        p = Permission.objects.get(
            codename='view_statistics', 
            content_type__app_label='freight'
        )
        self.user.user_permissions.add(p)
        self.user.save()

        request = self.factory.get(reverse(
            'freight:statistics_customer_data'
        ))
        request.user = self.user
        
        response = views.statistics_customer_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{'collaterals': '3,000', 'rewards': '300', 'corporation': 'Wayne Enterprise', 'contracts': '3', 'name': 'Robin'}]
        )


class TestAddLocation(TestCase):

    def setUp(self):
        self.user = create_contract_handler_w_contracts([])                
        self.factory = RequestFactory()
    
    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.views.messages_plus', autospec=True)    
    @patch(
        'freight.views.Location.objects.update_or_create_from_esi', 
        autospec=True
    )
    @patch('freight.views.esi_client_factory', autospec=True)
    def test_normal(
        self,                 
        mock_esi_client_factory,
        mock_update_or_create_from_esi,
        mock_message_plus
    ):          
        location_id = 1022167642188
        location = Location.objects.get(id=location_id)
        mock_update_or_create_from_esi.return_value = location, False
        
        my_character = self.user.profile.main_character        
        token = store_as_Token(
            generate_token(
                character_id=my_character.character_id,
                character_name=my_character.character_name,
                scopes=['publicData']
            ), 
            self.user
        )        
        request = self.factory.post(
            reverse('freight:add_location_2'),
            data={                
                'location_id': location_id
            }
        )
        request.user = self.user        
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session[views.ADD_LOCATION_TOKEN_TAG] = token.pk
        request.session.save()
        
        orig_view  = views.add_location_2\
            .__wrapped__.__wrapped__
        
        response = orig_view(request)        
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:add_location_2'))
        self.assertEqual(mock_message_plus.success.call_count, 1)
        self.assertEqual(mock_message_plus.error.call_count, 0)

    @patch(
        'freight.views.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch('freight.views.messages_plus', autospec=True)
    @patch(
        'freight.views.Location.objects.update_or_create_from_esi', 
        autospec=True
    )
    @patch('freight.views.esi_client_factory', autospec=True)
    def test_fetching_location_fails(
        self,                 
        mock_esi_client_factory,
        mock_update_or_create_from_esi,
        mock_message_plus
    ):          
        location_id = 1022167642188
        location = Location.objects.get(id=location_id)
        mock_update_or_create_from_esi.side_effect = \
            RuntimeError('Test exception')
        
        my_character = self.user.profile.main_character        
        token = store_as_Token(
            generate_token(
                character_id=my_character.character_id,
                character_name=my_character.character_name,
                scopes=['publicData']
            ), 
            self.user
        )        
        request = self.factory.post(
            reverse('freight:add_location_2'),
            data={                
                'location_id': location_id
            }
        )
        request.user = self.user        
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session[views.ADD_LOCATION_TOKEN_TAG] = token.pk
        request.session.save()
        
        orig_view  = views.add_location_2\
            .__wrapped__.__wrapped__
        
        response = orig_view(request)        
        self.assertEqual(response.status_code, HTTP_OK)        
        self.assertEqual(mock_message_plus.success.call_count, 0)
        self.assertEqual(mock_message_plus.error.call_count, 1)