import datetime
from unittest.mock import Mock, patch

from bravado.exception import HTTPNotFound, HTTPForbidden

from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.eveonline.providers import ObjectNotFound

from . import DisconnectPricingSaveHandler, get_invalid_object_pk
from ..app_settings import (
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_MY_CORPORATION,
    FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
    FREIGHT_OPERATION_MODE_CORP_PUBLIC
)
from ..models import Contract, EveEntity, Location, Pricing
from .testdata import (
    characters_data,    
    create_contract_handler_w_contracts,
    create_locations,
    structures_data, 
)
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'freight.managers'
logger = set_test_logger(MODULE_PATH, __file__)


class TestEveEntityManager(NoSocketsTestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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

    @patch('freight.helpers.provider')
    def test_alliance_not_found(self, mock_provider):
        mock_provider.client\
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
        self.assertEqual(int(corporation.id), 92000001)
        alliance, _ = \
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category=EveEntity.CATEGORY_ALLIANCE
            )
        self.assertEqual(int(alliance.id), 93000001)
        char2, _ = \
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category=EveEntity.CATEGORY_CHARACTER
            )
        self.assertEqual(int(char2.id), 90000001)
        with self.assertRaises(ValueError):
            EveEntity.objects.update_or_create_from_evecharacter(
                character,
                category='xxx'
            )


class TestLocationManager(NoSocketsTestCase):
    
    @classmethod
    def get_universe_stations_station_id(cls, *args, **kwargs) -> dict:    
        if 'station_id' not in kwargs:
            raise ValueError('missing parameter: station_id')
        
        station_id = str(kwargs['station_id'])
        if station_id not in structures_data:
            raise HTTPNotFound
        else:                
            m = Mock()
            m.result.return_value = structures_data[station_id]
            return m

    @classmethod
    def get_universe_structures_structure_id(cls, *args, **kwargs) -> dict:    
        if 'structure_id' not in kwargs:
            raise ValueError('missing parameter: structure_id')
        
        structure_id = str(kwargs['structure_id'])
        if structure_id not in structures_data:
            raise HTTPNotFound
        else:                
            m = Mock()
            m.result.return_value = structures_data[structure_id]
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


class TestContractManager(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts([
            149409016, 149409061, 149409062, 149409063, 149409064
        ])

    def test_update_pricing_bidirectional(self):
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        amarr = Location.objects.get(id=60008494)

        with DisconnectPricingSaveHandler():
            pricing_1 = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000,
                is_bidirectional=True
            )
            Pricing.objects.create(
                start_location=amamake,
                end_location=jita,
                price_base=350000000,
                is_bidirectional=True
            )
            pricing_3 = Pricing.objects.create(
                start_location=amarr,
                end_location=amamake,
                price_base=250000000,
                is_bidirectional=True
            )                
        Contract.objects.update_pricing()

        contract_1 = Contract.objects.get(contract_id=149409016)        
        self.assertEqual(contract_1.pricing, pricing_1)

        # pricing 2 should have been ignored, since it covers the same route
        contract_2 = Contract.objects.get(contract_id=149409061)
        self.assertEqual(contract_2.pricing, pricing_1)
                
        contract_3 = Contract.objects.get(contract_id=149409062)
        self.assertEqual(contract_3.pricing, pricing_3)

    def test_update_pricing_uni_directional(self):
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        amarr = Location.objects.get(id=60008494)
        
        with DisconnectPricingSaveHandler():
            pricing_1 = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000,
                is_bidirectional=False
            )
            pricing_2 = Pricing.objects.create(
                start_location=amamake,
                end_location=jita,
                price_base=350000000,
                is_bidirectional=False
            )
            pricing_3 = Pricing.objects.create(
                start_location=amarr,
                end_location=amamake,
                price_base=250000000,
                is_bidirectional=True
            )

        Contract.objects.update_pricing()

        contract_1 = Contract.objects.get(contract_id=149409016)        
        self.assertEqual(contract_1.pricing, pricing_1)
        
        contract_2 = Contract.objects.get(contract_id=149409061)
        self.assertEqual(contract_2.pricing, pricing_2)
                
        contract_3 = Contract.objects.get(contract_id=149409062)
        self.assertEqual(contract_3.pricing, pricing_3)

        contract_4 = Contract.objects.get(contract_id=149409063)
        self.assertEqual(contract_4.pricing, pricing_3)

        contract_5 = Contract.objects.get(contract_id=149409064)
        self.assertIsNone(contract_5.pricing)


@patch('freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS', 48)
@patch('freight.models.Webhook.execute', autospec=True)
class TestContractManagerNotifications(NoSocketsTestCase):
          
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, _ = create_contract_handler_w_contracts()        
        # disable pricing signal                
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)        
        with DisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000
            )
                
        Contract.objects.update_pricing() 
    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)    
    def test_send_pilot_notifications_normal(self, mock_webhook_execute):        
        logger.debug('test_send_pilot_notifications_normal - start')
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 8)
        logger.debug('test_send_pilot_notifications_normal - complete')
    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')        
    def test_send_customer_notifications_normal(self, mock_webhook_execute):
        logger.debug('test_send_customer_notifications_normal - start')
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 12)
        logger.debug('test_send_customer_notifications_normal - complete')

    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)    
    def test_dont_send_pilot_notifications_for_expired_contracts(
        self, mock_webhook_execute
    ):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')        
    def test_dont_send_customer_notifications_for_expired_contracts(
        self, mock_webhook_execute
    ):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - datetime.timedelta(hours=1)
        x.save()
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 0)
    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)    
    def test_send_pilot_notifications_only_once(
        self, mock_webhook_execute
    ):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()        
        
        # round #1
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)
    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 'url')        
    def test_send_customer_notifications_only_once_per_state(
        self, mock_webhook_execute
    ):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()        
        
        # round #1
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)
    
    @patch('freight.managers.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_WEBHOOK_URL', None)
    @patch('freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', None)    
    def test_dont_send_any_notifications_when_no_url_if_set(
        self, mock_webhook_execute
    ):        
        Contract.objects.send_notifications(rate_limted=False)        
        self.assertEqual(mock_webhook_execute.call_count, 0)


class TestPricingManager(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.jita, cls.amamake, cls.amarr = create_locations()

        with DisconnectPricingSaveHandler():
            cls.p1 = Pricing.objects.create(
                start_location=cls.jita,
                end_location=cls.amamake,
                price_base=50000000,
                is_default=True
            )
            cls.p2 = Pricing.objects.create(
                start_location=cls.jita,
                end_location=cls.amarr,
                price_base=10000000
            )

    def test_default_pricing_no_default_defined(self):                
        Pricing.objects.all().delete()
        with DisconnectPricingSaveHandler():
            p = Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=50000000,
                is_default=True
            )
        expected = p
        self.assertEqual(Pricing.objects.get_default(), expected)

    def test_default_and_default_defined(self):        
        expected = self.p1
        self.assertEqual(Pricing.objects.get_default(), expected)

    def test_default_with_no_pricing_defined(self):                
        Pricing.objects.all().delete()
        expected = None
        self.assertEqual(Pricing.objects.get_default(), expected)

    def test_get_or_default_normal(self):        
        expected = self.p1
        self.assertEqual(Pricing.objects.get_or_default(self.p1.pk), expected)

    def test_get_or_default_not_found(self):
        expected = self.p1
        invalid_pk = get_invalid_object_pk(Pricing)
        self.assertEqual(Pricing.objects.get_or_default(invalid_pk), expected)

    def test_get_or_default_with_none(self):        
        expected = self.p1        
        self.assertEqual(Pricing.objects.get_or_default(None), expected)
