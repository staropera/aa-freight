import datetime
import inspect
import json
import os
from random import randrange
from unittest.mock import Mock, patch

from django.contrib.auth.models import User, Permission 
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.authentication.models import CharacterOwnership
from allianceauth.services.modules.discord.models import DiscordUser
from esi.models import Token

from . import _set_logger
from ..app_settings import *
from ..models import *
from .. import views

logger = _set_logger('freight.views', __file__)

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))


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
        
        self.factory = RequestFactory()

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

        # user needs basic permission to access the app
        p = Permission.objects.get(
            codename='basic_access', 
            content_type__app_label='freight'
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
            if contract['type'] == 'courier':
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
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, 200)


    def test_contract_list_active_no_access_without_permission(self):
        request = self.factory.get(reverse('freight:contract_list_active'))
        request.user = self.user
        response = views.contract_list_active(request)
        self.assertNotEqual(response.status_code, 200)


    def test_contract_list_active_access_with_permission(self):
        p = Permission.objects.get(
            codename='view_contracts', 
            content_type__app_label='freight'
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
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode('utf-8'))        
        contract_ids = { x['contract_id'] for x in data }
        self.assertSetEqual(
            contract_ids, 
            {
                149409016
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
            content_type__app_label='freight'
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
        self.assertEqual(response.status_code, 200)

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
        self.assertEqual(response.status_code, 200)

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
        self.assertEqual(response.status_code, 200)

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
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode('utf-8'))        
        
        self.assertListEqual(
            data,
            [{'collaterals': '3,000', 'rewards': '300', 'corporation': 'Wayne Enterprise', 'contracts': '3', 'name': 'Robin'}]
        )
