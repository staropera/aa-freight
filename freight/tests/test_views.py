import json
from unittest.mock import Mock, patch

from django_webtest import WebTest

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from esi.models import Token

from . import TempDisconnectPricingSaveHandler, generate_token, store_as_Token
from ..app_settings import (
    FREIGHT_OPERATION_MODE_MY_ALLIANCE, FREIGHT_OPERATION_MODE_MY_CORPORATION
)
from ..models import Contract, ContractHandler, Location, Pricing
from .. import views
from .testdata import create_contract_handler_w_contracts
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'freight.views'
logger = set_test_logger(MODULE_PATH, __file__)

HTTP_OK = 200
HTTP_REDIRECT = 302


class TestCalculatorWeb(WebTest):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts()
        AuthUtils.add_permission_to_user_by_name(
            'freight.use_calculator', cls.user
        )        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)
            amarr = Location.objects.get(id=60008494)
            cls.pricing_1 = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=50000000,
                price_per_volume=150,
                price_per_collateral_percent=2,
                collateral_max=5000000000,
                volume_max=320000,
                days_to_complete=3,
                days_to_expire=7
            )
            cls.pricing_2 = Pricing.objects.create(
                start_location=jita,
                end_location=amarr,
                price_base=100000000
            )            
        Contract.objects.update_pricing() 
   
    def _calculate_price(
        self, pricing: Pricing, volume=None, collateral=None
    ) -> tuple:
        """Performs a full price query with the calculator
        
        returns tuple of price_str, form, request
        """
        self.app.set_user(self.user)
        # load page and get our form
        response = self.app.get(reverse('freight:calculator'))        
        form = None
        for _, obj in response.forms.items():
            if obj.id == 'form_calculator':
                form = obj        
        self.assertIsNotNone(form)
        
        # enter these values into form
        form['pricing'] = pricing.pk
        if volume:
            form['volume'] = volume
        if collateral:
            form['collateral'] = collateral
        
        # submit form and get response
        response = form.submit()
        form = None
        for _, obj in response.forms.items():
            if obj.id == 'form_calculator':
                form = obj        
        self.assertIsNotNone(form)
        
        # extract the price string
        price_str = response.html.find(id='text_price').string.strip()        
        return price_str, form, response

    def test_can_calculate_pricing_1(self):
        price_str, _, _ = self._calculate_price(self.pricing_1, 50000, 2000000000)
        expected = '98,000,000 ISK'
        self.assertEqual(price_str, expected)

    def test_can_calculate_pricing_2(self):
        price_str, _, _ = self._calculate_price(self.pricing_2)
        expected = '100,000,000 ISK'
        self.assertEqual(price_str, expected)

    def test_aborts_on_missing_collateral(self):
        price_str, form, _ = self._calculate_price(self.pricing_1, 50000)
        expected = '- ISK'
        self.assertEqual(price_str, expected)
        self.assertIn('Issues', form.text)
        self.assertIn('collateral is required', form.text)

    def test_aborts_on_missing_volume(self):
        price_str, form, _ = self._calculate_price(
            self.pricing_1, None, 500000
        )
        expected = '- ISK'
        self.assertEqual(price_str, expected)
        self.assertIn('Issues', form.text)
        self.assertIn('volume is required', form.text)

    def test_aborts_on_too_high_volume(self):
        price_str, form, _ = self._calculate_price(
            self.pricing_1, 400000, 500000
        )
        expected = '- ISK'
        self.assertEqual(price_str, expected)
        self.assertIn('Issues', form.text)
        self.assertIn('exceeds the maximum allowed volume', form.text)

    def test_aborts_on_too_high_collateral(self):
        price_str, form, _ = self._calculate_price(
            self.pricing_1, 40000, 6000000000
        )
        expected = '- ISK'
        self.assertEqual(price_str, expected)
        self.assertIn('Issues', form.text)
        self.assertIn('exceeds the maximum allowed collateral', form.text)


class TestCalculator(NoSocketsTestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts()
        AuthUtils.add_permission_to_user_by_name(
            'freight.use_calculator', cls.user
        )        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            cls.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        cls.factory = RequestFactory()

    def test_index(self):        
        request = self.factory.get(reverse('freight:index'))
        request.user = self.user
        response = views.index(request)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:calculator'))

    def test_calculator_access_with_permission(self):                
        request = self.factory.get(reverse('freight:calculator'))
        request.user = self.user
        response = views.calculator(request)
        self.assertEqual(response.status_code, HTTP_OK)

    def test_calculator_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:calculator'))
        request.user = AuthUtils.create_user('Lex Luthor')
        response = views.calculator(request)
        self.assertNotEqual(response.status_code, HTTP_OK)


class TestContractList(NoSocketsTestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user_1 = create_contract_handler_w_contracts()
        AuthUtils.add_permission_to_user_by_name(
            'freight.basic_access', cls.user_1
        ) 
        AuthUtils.add_permission_to_user_by_name(
            'freight.use_calculator', cls.user_1
        ) 
        AuthUtils.add_permission_to_user_by_name(
            'freight.view_contracts', cls.user_1
        )
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            cls.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        cls.factory = RequestFactory()
        cls.user_2 = AuthUtils.create_user('Lex Luthor')
        AuthUtils.add_permission_to_user_by_name(
            'freight.basic_access', cls.user_2
        ) 

    def test_active_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user_2
        response = views.contract_list_active(request)
        self.assertNotEqual(response.status_code, HTTP_OK)

    def test_active_access_with_permission(self):               
        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user_1
        
        response = views.contract_list_active(request)
        self.assertEqual(response.status_code, HTTP_OK)
    
    def test_data_activate(self):       
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_ACTIVE}
        ))
        request.user = self.user_1
        
        response = views.contract_list_data(
            request, 
            views.CONTRACT_LIST_ACTIVE
        )
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = {x['contract_id'] for x in data}
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
            'freight:contract_list_data', args={'this_is_not_valid'}
        ))
        request.user = self.user_1
        
        with self.assertRaises(ValueError):
            views.contract_list_data(
                request, 'this_is_not_valid'
            )
        
    def test_user_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user_2
        response = views.contract_list_user(request)
        self.assertNotEqual(response.status_code, HTTP_OK)

    def test_user_access_with_permission(self):        
        request = self.factory.get(reverse('freight:contract_list_user'))
        request.user = self.user_1
        
        response = views.contract_list_user(request)
        self.assertEqual(response.status_code, HTTP_OK)

    def test_data_user_no_access_without_permission_1(self):
        request = self.factory.get(reverse(
            'freight:contract_list_data', args={views.CONTRACT_LIST_USER}
        ))
        request.user = self.user_2
        
        with self.assertRaises(RuntimeError):
            views.contract_list_data(request, views.CONTRACT_LIST_USER)        

    def test_data_user_no_access_without_permission_2(self):
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_ACTIVE}
        ))
        request.user = self.user_2
        
        with self.assertRaises(RuntimeError):
            views.contract_list_data(request, views.CONTRACT_LIST_ACTIVE)
        
    def test_data_user(self):        
        request = self.factory.get(reverse(
            'freight:contract_list_data', 
            args={views.CONTRACT_LIST_USER}
        ))
        request.user = self.user_1
        
        response = views.contract_list_data(request, views.CONTRACT_LIST_USER)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = {x['contract_id'] for x in data}
        self.assertSetEqual(
            contract_ids, 
            {
                149409016, 149409061, 149409062, 149409063, 149409064,
            }
        )


class TestSetupContractHandler(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts([])
        AuthUtils.add_permission_to_user_by_name(
            'freight.setup_contract_handler', cls.user
        )        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            cls.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        cls.factory = RequestFactory()
    
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)
    @patch(MODULE_PATH + '.tasks.run_contracts_sync', autospec=True)
    def test_normal(self, mock_run_contracts_sync, mock_message_plus):
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
        
        orig_view = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)
        self.assertEqual(mock_run_contracts_sync.delay.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))

    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)
    @patch(MODULE_PATH + '.tasks.run_contracts_sync', autospec=True)
    def test_error_no_alliance_member(
        self, mock_run_contracts_sync, mock_message_plus
    ):       
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
        
        orig_view = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))

    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)
    @patch(MODULE_PATH + '.tasks.run_contracts_sync', autospec=True)
    def test_error_character_not_owned(
        self, mock_run_contracts_sync, mock_message_plus
    ):        
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
        
        orig_view = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))

    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_CORPORATION
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)
    @patch(MODULE_PATH + '.tasks.run_contracts_sync', autospec=True)
    def test_error_wrong_operation_mode(
        self, mock_run_contracts_sync, mock_message_plus
    ):       
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
        
        orig_view = views.setup_contract_handler\
            .__wrapped__.__wrapped__.__wrapped__ 
        
        response = orig_view(request, token)        
        self.assertEqual(mock_message_plus.error.call_count, 1)
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:index'))
    

class TestStatistics(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts()
        AuthUtils.add_permission_to_user_by_name(
            'freight.basic_access', cls.user
        )
        AuthUtils.add_permission_to_user_by_name(
            'freight.view_statistics', cls.user
        )        
        with TempDisconnectPricingSaveHandler():
            jita = Location.objects.get(id=60003760)
            amamake = Location.objects.get(id=1022167642188)      
            cls.pricing = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )        
        Contract.objects.update_pricing() 
        cls.factory = RequestFactory()

    def test_statistics_routes_data(self):        
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
        request = self.factory.get(reverse(
            'freight:statistics_pilots_data'
        ))
        request.user = self.user
        
        response = views.statistics_pilots_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{
                'collaterals': '3,000', 
                'rewards': '300', 
                'corporation': 'Wayne Enterprise', 
                'contracts': '3', 
                'name': 'Bruce Wayne'
            }]
        )

    def test_statistics_pilot_corporations_data(self):        
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
        request = self.factory.get(reverse(
            'freight:statistics_customer_data'
        ))
        request.user = self.user
        
        response = views.statistics_customer_data(request)
        self.assertEqual(response.status_code, HTTP_OK)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{
                'collaterals': '3,000', 
                'rewards': '300', 
                'corporation': 'Wayne Enterprise', 
                'contracts': '3', 
                'name': 'Robin'
            }]
        )


class TestAddLocation(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()    
        _, cls.user = create_contract_handler_w_contracts([])                
        cls.factory = RequestFactory()
    
    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)    
    @patch(
        MODULE_PATH + '.Location.objects.update_or_create_from_esi', 
        autospec=True
    )
    @patch(MODULE_PATH + '.esi_client_factory', autospec=True)
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
        
        orig_view = views.add_location_2\
            .__wrapped__.__wrapped__
        
        response = orig_view(request)        
        self.assertEqual(response.status_code, HTTP_REDIRECT)
        self.assertEqual(response.url, reverse('freight:add_location_2'))
        self.assertEqual(mock_message_plus.success.call_count, 1)
        self.assertEqual(mock_message_plus.error.call_count, 0)

    @patch(
        MODULE_PATH + '.FREIGHT_OPERATION_MODE', 
        FREIGHT_OPERATION_MODE_MY_ALLIANCE
    )
    @patch(MODULE_PATH + '.messages_plus', autospec=True)
    @patch(
        MODULE_PATH + '.Location.objects.update_or_create_from_esi', 
        autospec=True
    )
    @patch(MODULE_PATH + '.esi_client_factory', autospec=True)
    def test_fetching_location_fails(
        self,
        mock_esi_client_factory,
        mock_update_or_create_from_esi,
        mock_message_plus
    ):          
        location_id = 1022167642188
        Location.objects.get(id=location_id)
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
        
        orig_view = views.add_location_2\
            .__wrapped__.__wrapped__
        
        response = orig_view(request)        
        self.assertEqual(response.status_code, HTTP_OK)        
        self.assertEqual(mock_message_plus.success.call_count, 0)
        self.assertEqual(mock_message_plus.error.call_count, 1)
