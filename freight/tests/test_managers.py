from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from bravado.exception import HTTPNotFound, HTTPForbidden

from django.utils.timezone import now, utc

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound

from app_utils.django import app_labels
from app_utils.testing import NoSocketsTestCase
from esi.models import Token

from . import DisconnectPricingSaveHandler, get_invalid_object_pk
from ..app_settings import (
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_MY_CORPORATION,
    FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
    FREIGHT_OPERATION_MODE_CORP_PUBLIC,
)
from ..models import Contract, EveEntity, Location, Pricing
from .testdata import (
    characters_data,
    create_contract_handler_w_contracts,
    create_locations,
    structures_data,
    BravadoOperationStub,
)


MODULE_PATH = "freight.managers"


class TestEveEntityManager(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        esi_data = dict()
        for character in characters_data:
            esi_data[character["character_id"]] = {
                "id": character["character_id"],
                "category": EveEntity.CATEGORY_CHARACTER,
                "name": character["character_name"],
            }
            esi_data[character["corporation_id"]] = {
                "id": character["corporation_id"],
                "category": EveEntity.CATEGORY_CORPORATION,
                "name": character["corporation_name"],
            }
            esi_data[character["alliance_id"]] = {
                "id": character["alliance_id"],
                "category": EveEntity.CATEGORY_ALLIANCE,
                "name": character["alliance_name"],
            }
            EveCharacter.objects.create(**character)

        cls.esi_data = esi_data
        cls.character = EveCharacter.objects.get(character_id=90000001)

    @classmethod
    def esi_post_universe_names(cls, *args, **kwargs) -> list:
        data = list()
        if "ids" not in kwargs:
            raise ValueError("missing parameter: ids")
        for id in kwargs["ids"]:
            if id in cls.esi_data:
                data.append(cls.esi_data[id])

        return BravadoOperationStub(data)

    @patch("freight.helpers.esi_fetch._esi_client")
    def test_can_create_entity(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            TestEveEntityManager.esi_post_universe_names
        )

        obj, created = EveEntity.objects.update_or_create_from_esi(id=90000001)
        self.assertTrue(created)
        self.assertEqual(obj.id, 90000001)
        self.assertEqual(obj.name, "Bruce Wayne")
        self.assertEqual(obj.category, EveEntity.CATEGORY_CHARACTER)

    @patch("freight.helpers.esi_fetch._esi_client")
    def test_can_create_entity_when_not_found(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            TestEveEntityManager.esi_post_universe_names
        )

        obj, created = EveEntity.objects.get_or_create_from_esi(id=90000001)
        self.assertTrue(created)
        self.assertEqual(obj.id, 90000001)
        self.assertEqual(obj.name, "Bruce Wayne")
        self.assertEqual(obj.category, EveEntity.CATEGORY_CHARACTER)

    @patch("freight.helpers.esi_fetch._esi_client")
    def test_can_update_entity(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            TestEveEntityManager.esi_post_universe_names
        )
        obj, _ = EveEntity.objects.update_or_create_from_esi(id=90000001)
        obj.name = "Blue Company"
        obj.category = EveEntity.CATEGORY_CORPORATION

        obj, created = EveEntity.objects.update_or_create_from_esi(id=90000001)
        self.assertFalse(created)
        self.assertEqual(obj.id, 90000001)
        self.assertEqual(obj.name, "Bruce Wayne")
        self.assertEqual(obj.category, EveEntity.CATEGORY_CHARACTER)

    @patch("freight.helpers.esi_fetch._esi_client")
    def test_raise_exception_if_entity_can_not_be_created(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            TestEveEntityManager.esi_post_universe_names
        )

        with self.assertRaises(ObjectNotFound):
            entity, _ = EveEntity.objects.get_or_create_from_esi(id=666)

    def test_can_return_category_for_operation_mode(self):
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_MY_ALLIANCE
            ),
            EveEntity.CATEGORY_ALLIANCE,
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_MY_CORPORATION
            ),
            EveEntity.CATEGORY_CORPORATION,
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
            ),
            EveEntity.CATEGORY_CORPORATION,
        )
        self.assertEqual(
            EveEntity.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE_CORP_PUBLIC
            ),
            EveEntity.CATEGORY_CORPORATION,
        )

    def test_can_create_corporation_from_evecharacter(self):
        corporation, _ = EveEntity.objects.update_or_create_from_evecharacter(
            self.character, category=EveEntity.CATEGORY_CORPORATION
        )
        self.assertEqual(int(corporation.id), 92000001)

    def test_can_create_alliance_from_evecharacter(self):
        alliance, _ = EveEntity.objects.update_or_create_from_evecharacter(
            self.character, category=EveEntity.CATEGORY_ALLIANCE
        )
        self.assertEqual(int(alliance.id), 93000001)

    def test_can_create_character_alliance_from_evecharacter(self):
        char2, _ = EveEntity.objects.update_or_create_from_evecharacter(
            self.character, category=EveEntity.CATEGORY_CHARACTER
        )
        self.assertEqual(int(char2.id), 90000001)

    def test_raises_exception_when_trying_to_create_alliance_from_non_member(self):
        character = EveCharacter.objects.get(character_id=90000005)
        with self.assertRaises(ValueError):
            EveEntity.objects.update_or_create_from_evecharacter(
                character, category=EveEntity.CATEGORY_ALLIANCE
            )

    def test_raises_exception_when_trying_to_create_invalid_category_from_evechar(self):
        with self.assertRaises(ValueError):
            EveEntity.objects.update_or_create_from_evecharacter(
                self.character, category="xxx"
            )


def get_universe_stations_station_id(*args, **kwargs) -> dict:
    if "station_id" not in kwargs:
        raise ValueError("missing parameter: station_id")

    station_id = str(kwargs["station_id"])
    if station_id not in structures_data:
        raise HTTPNotFound
    else:
        return BravadoOperationStub(structures_data[station_id])


def get_universe_structures_structure_id(*args, **kwargs) -> dict:
    if "structure_id" not in kwargs:
        raise ValueError("missing parameter: structure_id")

    structure_id = str(kwargs["structure_id"])
    if structure_id not in structures_data:
        raise HTTPNotFound
    else:
        return BravadoOperationStub(structures_data[structure_id])


@patch("freight.helpers.esi_fetch._esi_client")
class TestLocationManager(NoSocketsTestCase):
    def test_can_create_structure(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            get_universe_structures_structure_id
        )

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 1000000000001)
        self.assertEqual(obj.name, "Test Structure Alpha")
        self.assertEqual(obj.solar_system_id, 30002537)
        self.assertEqual(obj.type_id, 35832)

    def test_can_update_structure(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            get_universe_structures_structure_id
        )
        obj, _ = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )
        obj.name = "Not my structure"
        obj.solar_system_id = 123
        obj.type_id = 456
        obj.save()

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )
        self.assertFalse(created)
        self.assertEqual(obj.id, 1000000000001)
        self.assertEqual(obj.name, "Test Structure Alpha")
        self.assertEqual(obj.solar_system_id, 30002537)
        self.assertEqual(obj.type_id, 35832)

    def test_can_get_existing_location(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            get_universe_structures_structure_id
        )
        obj_created, _ = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )

        obj, created = Location.objects.get_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )
        self.assertFalse(created)
        self.assertEqual(obj, obj_created)

    def test_can_create_not_existing_location(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            get_universe_structures_structure_id
        )

        obj, created = Location.objects.get_or_create_from_esi(
            Mock(spec=Token), 1000000000001
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 1000000000001)
        self.assertEqual(obj.name, "Test Structure Alpha")
        self.assertEqual(obj.solar_system_id, 30002537)
        self.assertEqual(obj.type_id, 35832)

    def test_propagates_http_error_on_structure_create(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = HTTPForbidden(
            Mock()
        )

        with self.assertRaises(HTTPForbidden):
            Location.objects.update_or_create_from_esi(
                Mock(spec=Token), 42, add_unknown=False
            )

    def test_propagates_exceptions_on_structure_create(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            RuntimeError
        )

        with self.assertRaises(RuntimeError):
            Location.objects.update_or_create_from_esi(
                Mock(spec=Token), 42, add_unknown=False
            )

    def test_creates_skeleton_structure_on_http_error_if_requested(
        self, mock_esi_client
    ):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = HTTPForbidden(
            Mock()
        )

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 42, add_unknown=True
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 42)

    def test_does_not_creates_skeleton_structure_on_exceptions_if_requested(
        self, mock_esi_client
    ):
        mock_esi_client.return_value.Universe.get_universe_structures_structure_id.side_effect = (
            RuntimeError
        )
        with self.assertRaises(RuntimeError):
            Location.objects.update_or_create_from_esi(
                Mock(spec=Token), 42, add_unknown=True
            )

    def test_can_create_station(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_stations_station_id.side_effect = (
            get_universe_stations_station_id
        )

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 60000001
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 60000001)
        self.assertEqual(obj.name, "Test Station Charlie")
        self.assertEqual(obj.solar_system_id, 30002537)
        self.assertEqual(obj.type_id, 99)

    def test_can_update_station(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_stations_station_id.side_effect = (
            get_universe_stations_station_id
        )

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 60000001
        )
        obj.name = "Not my station"
        obj.solar_system_id = 123
        obj.type_id = 456
        obj.save()

        obj, created = Location.objects.update_or_create_from_esi(
            Mock(spec=Token), 60000001
        )
        self.assertFalse(created)
        self.assertEqual(obj.id, 60000001)
        self.assertEqual(obj.name, "Test Station Charlie")
        self.assertEqual(obj.solar_system_id, 30002537)
        self.assertEqual(obj.type_id, 99)

    def test_propagates_http_error_on_station_create(self, mock_esi_client):
        mock_esi_client.return_value.Universe.get_universe_stations_station_id.side_effect = HTTPNotFound(
            Mock()
        )

        with self.assertRaises(HTTPNotFound):
            Location.objects.update_or_create_from_esi(
                Mock(spec=Token), 60000001, add_unknown=False
            )


class TestContractQuerySet(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, cls.user = create_contract_handler_w_contracts(
            [149409016, 149409061, 149409062, 149409063, 149409064, 149409006]
        )

    def test_pending_count(self):
        result = Contract.objects.all().pending_count()
        self.assertEqual(result, 6)


class TestContractManager(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, cls.user = create_contract_handler_w_contracts(
            [149409016, 149409061, 149409062, 149409063, 149409064, 149409006]
        )

    def test_issued_by_user(self):
        qs = Contract.objects.issued_by_user(user=self.user)
        self.assertSetEqual(
            set(qs.values_list("contract_id", flat=True)),
            {149409016, 149409061, 149409062, 149409063, 149409064},
        )

    def test_can_update_pricing_for_bidirectional(self):
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        amarr = Location.objects.get(id=60008494)

        with DisconnectPricingSaveHandler():
            pricing_1 = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000,
                is_bidirectional=True,
            )
            Pricing.objects.create(
                start_location=amamake,
                end_location=jita,
                price_base=350000000,
                is_bidirectional=True,
            )
            pricing_3 = Pricing.objects.create(
                start_location=amarr,
                end_location=amamake,
                price_base=250000000,
                is_bidirectional=True,
            )
        Contract.objects.update_pricing()

        contract_1 = Contract.objects.get(contract_id=149409016)
        self.assertEqual(contract_1.pricing, pricing_1)

        # pricing 2 should have been ignored, since it covers the same route
        contract_2 = Contract.objects.get(contract_id=149409061)
        self.assertEqual(contract_2.pricing, pricing_1)

        contract_3 = Contract.objects.get(contract_id=149409062)
        self.assertEqual(contract_3.pricing, pricing_3)

    def test_can_update_pricing_for_unidirectional(self):
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        amarr = Location.objects.get(id=60008494)

        with DisconnectPricingSaveHandler():
            pricing_1 = Pricing.objects.create(
                start_location=jita,
                end_location=amamake,
                price_base=500000000,
                is_bidirectional=False,
            )
            pricing_2 = Pricing.objects.create(
                start_location=amamake,
                end_location=jita,
                price_base=350000000,
                is_bidirectional=False,
            )
            pricing_3 = Pricing.objects.create(
                start_location=amarr,
                end_location=amamake,
                price_base=250000000,
                is_bidirectional=True,
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


class TestContractManagerCreateFromDict(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, cls.user = create_contract_handler_w_contracts(
            [149409016, 149409061, 149409062, 149409063, 149409064]
        )

    def test_can_create_outstanding(self):
        contract_dict = {
            "acceptor_id": 0,
            "assignee_id": 93000001,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": None,
            "date_completed": None,
            "date_expired": datetime(2019, 10, 30, 23, tzinfo=utc),
            "date_issued": datetime(2019, 10, 2, 23, tzinfo=utc),
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "outstanding",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        obj, created = Contract.objects.update_or_create_from_dict(
            self.handler, contract_dict, Mock()
        )
        self.assertTrue(created)
        self.assertEqual(obj.contract_id, 149409014)
        self.assertIsNone(obj.acceptor)
        self.assertIsNone(obj.acceptor_corporation)
        self.assertEqual(obj.collateral, 50000000)
        self.assertIsNone(obj.date_accepted)
        self.assertIsNone(obj.date_completed)
        self.assertEqual(obj.date_expired, datetime(2019, 10, 30, 23, tzinfo=utc))
        self.assertEqual(obj.date_issued, datetime(2019, 10, 2, 23, tzinfo=utc))
        self.assertEqual(obj.days_to_complete, 3)
        self.assertEqual(obj.end_location_id, 1022167642188)
        self.assertFalse(obj.for_corporation)
        self.assertEqual(
            obj.issuer_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )
        self.assertEqual(obj.issuer, EveCharacter.objects.get(character_id=90000003))
        self.assertEqual(obj.reward, 25000000)
        self.assertEqual(obj.start_location_id, 60003760)
        self.assertEqual(obj.status, Contract.STATUS_OUTSTANDING)
        self.assertEqual(obj.title, "demo contract")
        self.assertEqual(obj.volume, 115000)
        self.assertIsNone(obj.pricing)
        self.assertIsNone(obj.issues)

    def test_can_create_in_progress(self):
        contract_dict = {
            "acceptor_id": 90000003,
            "assignee_id": 90000003,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": datetime(2019, 10, 3, 23, tzinfo=utc),
            "date_completed": None,
            "date_expired": datetime(2019, 10, 30, 23, tzinfo=utc),
            "date_issued": datetime(2019, 10, 2, 23, tzinfo=utc),
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "in_progress",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        obj, created = Contract.objects.update_or_create_from_dict(
            self.handler, contract_dict, Mock()
        )
        self.assertTrue(created)
        self.assertEqual(obj.contract_id, 149409014)
        self.assertEqual(obj.acceptor, EveCharacter.objects.get(character_id=90000003))
        self.assertEqual(
            obj.acceptor_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )
        self.assertEqual(obj.collateral, 50000000)
        self.assertEqual(obj.date_accepted, datetime(2019, 10, 3, 23, tzinfo=utc))
        self.assertIsNone(obj.date_completed)
        self.assertEqual(obj.date_issued, datetime(2019, 10, 2, 23, tzinfo=utc))
        self.assertEqual(obj.date_expired, datetime(2019, 10, 30, 23, tzinfo=utc))
        self.assertEqual(obj.days_to_complete, 3)
        self.assertEqual(obj.end_location_id, 1022167642188)
        self.assertFalse(obj.for_corporation)
        self.assertEqual(
            obj.issuer_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )
        self.assertEqual(obj.issuer, EveCharacter.objects.get(character_id=90000003))
        self.assertEqual(obj.reward, 25000000)
        self.assertEqual(obj.start_location_id, 60003760)
        self.assertEqual(obj.status, Contract.STATUS_IN_PROGRESS)
        self.assertEqual(obj.title, "demo contract")
        self.assertEqual(obj.volume, 115000)
        self.assertIsNone(obj.pricing)
        self.assertIsNone(obj.issues)

    def test_can_create_finished(self):
        contract_dict = {
            "acceptor_id": 90000003,
            "assignee_id": 90000003,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": datetime(2019, 10, 3, 23, tzinfo=utc),
            "date_completed": datetime(2019, 10, 4, 23, tzinfo=utc),
            "date_expired": datetime(2019, 10, 30, 23, tzinfo=utc),
            "date_issued": datetime(2019, 10, 2, 23, tzinfo=utc),
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "finished",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        obj, created = Contract.objects.update_or_create_from_dict(
            self.handler, contract_dict, Mock()
        )
        self.assertTrue(created)
        self.assertEqual(obj.contract_id, 149409014)
        self.assertEqual(obj.acceptor, EveCharacter.objects.get(character_id=90000003))
        self.assertEqual(
            obj.acceptor_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )
        self.assertEqual(obj.collateral, 50000000)
        self.assertEqual(obj.date_accepted, datetime(2019, 10, 3, 23, tzinfo=utc))
        self.assertEqual(obj.date_completed, datetime(2019, 10, 4, 23, tzinfo=utc))
        self.assertEqual(obj.date_issued, datetime(2019, 10, 2, 23, tzinfo=utc))
        self.assertEqual(obj.date_expired, datetime(2019, 10, 30, 23, tzinfo=utc))
        self.assertEqual(obj.days_to_complete, 3)
        self.assertEqual(obj.end_location_id, 1022167642188)
        self.assertFalse(obj.for_corporation)
        self.assertEqual(
            obj.issuer_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )
        self.assertEqual(obj.issuer, EveCharacter.objects.get(character_id=90000003))
        self.assertEqual(obj.reward, 25000000)
        self.assertEqual(obj.start_location_id, 60003760)
        self.assertEqual(obj.status, Contract.STATUS_FINISHED)
        self.assertEqual(obj.title, "demo contract")
        self.assertEqual(obj.volume, 115000)
        self.assertIsNone(obj.pricing)
        self.assertIsNone(obj.issues)

    def test_raises_exception_on_wrong_date_types(self):
        contract_dict = {
            "acceptor_id": 90000003,
            "assignee_id": 90000003,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": "2019-10-03T23:00:00Z",
            "date_completed": "2019-10-04T23:00:00Z",
            "date_expired": "2019-10-30T23:00:00Z",
            "date_issued": "2019-10-02T23:00:00Z",
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "finished",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        with self.assertRaises(TypeError):
            Contract.objects.update_or_create_from_dict(
                self.handler, contract_dict, Mock()
            )

    @patch(MODULE_PATH + ".EveCharacter.objects.create_character")
    def test_can_create_in_progress_and_creates_acceptor_char(
        self, mock_create_character
    ):
        def create_character(character_id):
            return EveCharacter.objects.create(
                character_id=90000987,
                character_name="Dummy",
                corporation_id=92000002,
                corporation_name="The Planet",
            )

        mock_create_character.side_effect = create_character
        EveEntity.objects.create(
            id=90000987, name="Dummy", category=EveEntity.CATEGORY_CHARACTER
        )
        contract_dict = {
            "acceptor_id": 90000987,
            "assignee_id": 90000987,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": datetime(2019, 10, 3, 23, tzinfo=utc),
            "date_completed": None,
            "date_expired": datetime(2019, 10, 30, 23, tzinfo=utc),
            "date_issued": datetime(2019, 10, 2, 23, tzinfo=utc),
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "in_progress",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        obj, created = Contract.objects.update_or_create_from_dict(
            self.handler, contract_dict, Mock()
        )
        self.assertTrue(created)
        self.assertEqual(obj.contract_id, 149409014)
        self.assertEqual(obj.acceptor, EveCharacter.objects.get(character_id=90000987))
        self.assertEqual(
            obj.acceptor_corporation,
            EveCorporationInfo.objects.get(corporation_id=92000002),
        )

    @patch(MODULE_PATH + ".EveCharacter.objects.create_character")
    def test_sets_acceptor_to_none_if_it_cant_be_created(self, mock_create_character):
        mock_create_character.side_effect = RuntimeError
        EveEntity.objects.create(
            id=90000987, name="Dummy", category=EveEntity.CATEGORY_CHARACTER
        )
        contract_dict = {
            "acceptor_id": 90000987,
            "assignee_id": 90000987,
            "availability": "personal",
            "buyout": None,
            "collateral": 50000000.0,
            "contract_id": 149409014,
            "date_accepted": datetime(2019, 10, 3, 23, tzinfo=utc),
            "date_completed": None,
            "date_expired": datetime(2019, 10, 30, 23, tzinfo=utc),
            "date_issued": datetime(2019, 10, 2, 23, tzinfo=utc),
            "days_to_complete": 3,
            "end_location_id": 1022167642188,
            "for_corporation": False,
            "issuer_corporation_id": 92000002,
            "issuer_id": 90000003,
            "price": 0.0,
            "reward": 25000000.0,
            "start_location_id": 60003760,
            "status": "in_progress",
            "title": "demo contract",
            "type": "courier",
            "volume": 115000.0,
        }
        obj, created = Contract.objects.update_or_create_from_dict(
            self.handler, contract_dict, Mock()
        )
        self.assertTrue(created)
        self.assertEqual(obj.contract_id, 149409014)
        self.assertIsNone(obj.acceptor)
        self.assertIsNone(obj.acceptor_corporation)


@patch("freight.models.FREIGHT_HOURS_UNTIL_STALE_STATUS", 48)
@patch("freight.models.Webhook.execute", autospec=True)
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
                start_location=jita, end_location=amamake, price_base=500000000
            )

        Contract.objects.update_pricing()

    @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    def test_send_pilot_notifications_normal(self, mock_webhook_execute):
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 8)

    @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    def test_dont_send_pilot_notifications_for_expired_contracts(
        self, mock_webhook_execute
    ):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()
        x.date_expired = now() - timedelta(hours=1)
        x.save()
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    def test_send_pilot_notifications_only_once(self, mock_webhook_execute):
        x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
        Contract.objects.all().exclude(pk=x.pk).delete()

        # round #1
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)

        # round #2
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", None)
    @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", None)
    @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    def test_dont_send_any_notifications_when_no_url_if_set(self, mock_webhook_execute):
        Contract.objects.send_notifications(rate_limted=False)
        self.assertEqual(mock_webhook_execute.call_count, 0)

    if "discord" in app_labels():

        @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
        @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
        def test_send_customer_notifications_normal(self, mock_webhook_execute):
            Contract.objects.send_notifications(rate_limted=False)
            self.assertEqual(mock_webhook_execute.call_count, 12)

        @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
        @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
        def test_dont_send_customer_notifications_for_expired_contracts(
            self, mock_webhook_execute
        ):
            x = Contract.objects.filter(status=Contract.STATUS_OUTSTANDING).first()
            Contract.objects.all().exclude(pk=x.pk).delete()
            x.date_expired = now() - timedelta(hours=1)
            x.save()
            Contract.objects.send_notifications(rate_limted=False)
            self.assertEqual(mock_webhook_execute.call_count, 0)

        @patch("freight.managers.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.managers.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
        @patch("freight.models.FREIGHT_DISCORD_WEBHOOK_URL", None)
        @patch("freight.models.FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
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
                is_default=True,
            )
            cls.p2 = Pricing.objects.create(
                start_location=cls.jita, end_location=cls.amarr, price_base=10000000
            )

    def test_default_pricing_no_default_defined(self):
        Pricing.objects.all().delete()
        with DisconnectPricingSaveHandler():
            p = Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=50000000,
                is_default=True,
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
