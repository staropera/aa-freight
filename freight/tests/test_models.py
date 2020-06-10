from datetime import timedelta
from unittest.mock import patch, Mock
import math

from dhooks_lite import Embed

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.services.modules.discord.models import DiscordUser
from allianceauth.tests.auth_utils import AuthUtils

from esi.models import Token
from esi.errors import TokenExpiredError, TokenInvalidError

from . import DisconnectPricingSaveHandler
from ..app_settings import (
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_MY_CORPORATION,
    FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
    FREIGHT_OPERATION_MODE_CORP_PUBLIC,
    FREIGHT_OPERATION_MODES,
)
from ..models import (
    Contract,
    ContractCustomerNotification,
    ContractHandler,
    EveEntity,
    Location,
    Pricing,
)
from .testdata import (
    characters_data,
    create_locations,
    create_entities_from_characters,
    create_contract_handler_w_contracts,
    contracts_data,
)
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = "freight.models"
PATCH_FREIGHT_OPERATION_MODE = MODULE_PATH + ".FREIGHT_OPERATION_MODE"
logger = set_test_logger(MODULE_PATH, __file__)


class TestPricing(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, _ = create_contract_handler_w_contracts()
        cls.jita = Location.objects.get(id=60003760)
        cls.amamake = Location.objects.get(id=1022167642188)
        cls.amarr = Location.objects.get(id=60008494)

    @patch(MODULE_PATH + ".FREIGHT_FULL_ROUTE_NAMES", False)
    def test_str(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        expected = "Jita <-> Amamake"
        self.assertEqual(str(p), expected)

    def test_repr(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        expected = (
            "Pricing(pk={}, "
            "name='Jita IV - Moon 4 - Caldari Navy Assembly Plant "
            "<-> Amamake - 3 Time Nearly AT Winners')"
        ).format(p.pk)
        self.assertEqual(repr(p), expected)

    @patch(MODULE_PATH + ".FREIGHT_FULL_ROUTE_NAMES", False)
    def test_name_from_settings_short(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        self.assertEqual(p.name, "Jita <-> Amamake")

    def test_name_short(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        self.assertEqual(p.name_short, "Jita <-> Amamake")

    @patch(MODULE_PATH + ".FREIGHT_FULL_ROUTE_NAMES", True)
    def test_name_from_settings_full(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        self.assertEqual(
            p.name,
            "Jita IV - Moon 4 - Caldari Navy Assembly Plant <-> "
            "Amamake - 3 Time Nearly AT Winners",
        )

    def test_name_full(self):
        p = Pricing(
            start_location=self.jita, end_location=self.amamake, price_base=50000000
        )
        self.assertEqual(
            p.name_full,
            "Jita IV - Moon 4 - Caldari Navy Assembly Plant <-> "
            "Amamake - 3 Time Nearly AT Winners",
        )

    def test_create_pricings(self):
        with DisconnectPricingSaveHandler():
            # first pricing
            Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
            )
            # pricing with different route
            Pricing.objects.create(
                start_location=self.amarr,
                end_location=self.amamake,
                price_base=250000000,
            )
            # pricing with reverse route then pricing 1
            Pricing.objects.create(
                start_location=self.amamake,
                end_location=self.jita,
                price_base=350000000,
            )

    def test_create_pricing_no_2nd_bidirectional_allowed(self):
        with DisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
                is_bidirectional=True,
            )
            p = Pricing.objects.create(
                start_location=self.amamake,
                end_location=self.jita,
                price_base=500000000,
                is_bidirectional=True,
            )
            with self.assertRaises(ValidationError):
                p.clean()

    def test_create_pricing_no_2nd_unidirectional_allowed(self):
        with DisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
                is_bidirectional=True,
            )
            p = Pricing.objects.create(
                start_location=self.amamake,
                end_location=self.jita,
                price_base=500000000,
                is_bidirectional=False,
            )
            p.clean()
            # this test case has been temporary inverted to allow users
            # to migrate their pricings
            """
            with self.assertRaises(ValidationError):
                p.clean()
            """

    def test_create_pricing_2nd_must_be_unidirectional_a(self):
        with DisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
                is_bidirectional=False,
            )
            p = Pricing.objects.create(
                start_location=self.amamake,
                end_location=self.jita,
                price_base=500000000,
                is_bidirectional=True,
            )
            with self.assertRaises(ValidationError):
                p.clean()

    def test_create_pricing_2nd_ok_when_unidirectional(self):
        with DisconnectPricingSaveHandler():
            Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
                is_bidirectional=False,
            )
            p = Pricing.objects.create(
                start_location=self.amamake,
                end_location=self.jita,
                price_base=500000000,
                is_bidirectional=False,
            )
            p.clean()

    def test_name_uni_directional(self):
        p = Pricing(
            start_location=self.jita,
            end_location=self.amamake,
            price_base=50000000,
            is_bidirectional=False,
        )
        self.assertEqual(p.name, "Jita -> Amamake")

    def test_get_calculated_price(self):
        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(p.get_calculated_price(10, 0), 500)

        p = Pricing()
        p.price_per_collateral_percent = 2
        self.assertEqual(p.get_calculated_price(10, 1000), 20)

        p = Pricing()
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        self.assertEqual(p.get_calculated_price(10, 1000), 520)

        p = Pricing()
        p.price_base = 20
        self.assertEqual(p.get_calculated_price(10, 1000), 20)

        p = Pricing()
        p.price_min = 1000
        self.assertEqual(p.get_calculated_price(10, 1000), 1000)

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        self.assertEqual(p.get_calculated_price(10, 1000), 520)

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_min = 1000
        self.assertEqual(p.get_calculated_price(10, 1000), 1000)

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        p.price_min = 500
        self.assertEqual(p.get_calculated_price(10, 1000), 540)

        with self.assertRaises(ValueError):
            p.get_calculated_price(-5, 0)

        with self.assertRaises(ValueError):
            p.get_calculated_price(50, -5)

        p = Pricing()
        p.price_base = 0
        self.assertEqual(p.get_calculated_price(None, None), 0)

        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(p.get_calculated_price(10, None), 500)

        p = Pricing()
        p.price_per_collateral_percent = 2
        self.assertEqual(p.get_calculated_price(None, 100), 2)

    def test_get_contract_pricing_errors(self):
        p = Pricing()
        p.price_base = 50
        self.assertIsNone(p.get_contract_price_check_issues(10, 20, 50))

        p = Pricing()
        p.price_base = 500
        p.volume_max = 300
        self.assertIsNotNone(p.get_contract_price_check_issues(350, 1000))

        p = Pricing()
        p.price_base = 500
        p.volume_min = 100
        self.assertIsNotNone(p.get_contract_price_check_issues(50, 1000))

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
        self.assertEqual(p.get_calculated_price(350, 0), 500)

    def test_requires_volume(self):
        self.assertTrue(Pricing(price_per_volume=10000).requires_volume())
        self.assertTrue(Pricing(volume_min=10000).requires_volume())
        self.assertTrue(
            Pricing(price_per_volume=10000, volume_min=10000).requires_volume()
        )
        self.assertFalse(Pricing().requires_volume())

    def test_requires_collateral(self):
        self.assertTrue(Pricing(price_per_collateral_percent=2).requires_collateral())
        self.assertTrue(Pricing(collateral_min=50000000).requires_collateral())
        self.assertTrue(
            Pricing(
                price_per_collateral_percent=2, collateral_min=50000000
            ).requires_collateral()
        )
        self.assertFalse(Pricing().requires_collateral())

    def test_clean_force_error(self):
        p = Pricing()
        with self.assertRaises(ValidationError):
            p.clean()

    def test_is_fix_price(self):
        self.assertTrue(Pricing(price_base=50000000).is_fix_price())
        self.assertFalse(
            Pricing(price_base=50000000, price_min=40000000).is_fix_price()
        )
        self.assertFalse(
            Pricing(price_base=50000000, price_per_volume=400).is_fix_price()
        )
        self.assertFalse(
            Pricing(price_base=50000000, price_per_collateral_percent=2).is_fix_price()
        )
        self.assertFalse(Pricing().is_fix_price())

    def test_clean_normal(self):
        p = Pricing(price_base=50000000)
        p.clean()


class TestPricingPricePerVolumeModifier(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, _ = create_contract_handler_w_contracts()

    def test_return_none_if_not_set(self):
        p = Pricing()
        self.assertIsNone(p.price_per_volume_modifier())
        self.assertIsNone(p.price_per_volume_eff())

    def test_is_ignored_in_price_calculation_if_not_set(self):
        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(p.get_calculated_price(10, None), 500)

    def test_returns_none_if_not_set_in_pricing(self):
        self.handler.price_per_volume_modifier = 10
        self.handler.save()
        p = Pricing()
        p.price_per_volume = 50

        self.assertIsNone(p.price_per_volume_modifier())

    def test_can_calculate_with_plus_value(self):
        self.handler.price_per_volume_modifier = 10
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(p.price_per_volume_eff(), 55)
        self.assertEqual(p.get_calculated_price(10, None), 550)

    def test_can_calculate_with_negative_value(self):
        self.handler.price_per_volume_modifier = -10
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(p.price_per_volume_eff(), 45)
        self.assertEqual(p.get_calculated_price(10, None), 450)

    def test_calculated_price_is_never_negative(self):
        self.handler.price_per_volume_modifier = -200
        self.handler.save()

        p = Pricing()
        p.price_per_volume = 50
        p.use_price_per_volume_modifier = True

        self.assertEqual(p.price_per_volume_eff(), 0)

    def test_returns_none_if_not_set_for_handler(self):
        p = Pricing(price_base=50000000)
        p.use_price_per_volume_modifier = True
        self.assertIsNone(p.price_per_volume_modifier())

    def test_returns_none_if_no_handler_defined(self):
        ContractHandler.objects.all().delete()
        p = Pricing(price_base=50000000)
        p.use_price_per_volume_modifier = True
        self.assertIsNone(p.price_per_volume_modifier())


class TestContract(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for character in characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character["corporation_id"],
                defaults={
                    "corporation_name": character["corporation_name"],
                    "corporation_ticker": character["corporation_ticker"],
                    "member_count": 42,
                },
            )

        # 1 user
        cls.character = EveCharacter.objects.get(character_id=90000001)
        cls.corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.character.corporation_id
        )
        cls.organization = EveEntity.objects.create(
            id=cls.character.alliance_id,
            category=EveEntity.CATEGORY_ALLIANCE,
            name=cls.character.alliance_name,
        )
        cls.user = User.objects.create_user(
            cls.character.character_name, "abc@example.com", "password"
        )
        cls.main_ownership = CharacterOwnership.objects.create(
            character=cls.character, owner_hash="x1", user=cls.user
        )
        # Locations
        cls.jita = Location.objects.create(
            id=60003760,
            name="Jita IV - Moon 4 - Caldari Navy Assembly Plant",
            solar_system_id=30000142,
            type_id=52678,
            category_id=3,
        )
        cls.amamake = Location.objects.create(
            id=1022167642188,
            name="Amamake - 3 Time Nearly AT Winners",
            solar_system_id=30002537,
            type_id=35834,
            category_id=65,
        )
        cls.handler = ContractHandler.objects.create(
            organization=cls.organization, character=cls.main_ownership
        )

    def setUp(self):
        # create contracts
        with DisconnectPricingSaveHandler():
            self.pricing = Pricing.objects.create(
                start_location=self.jita,
                end_location=self.amamake,
                price_base=500000000,
            )
        self.contract = Contract.objects.create(
            handler=self.handler,
            contract_id=1,
            collateral=0,
            date_issued=now(),
            date_expired=now() + timedelta(days=5),
            days_to_complete=3,
            end_location=self.amamake,
            for_corporation=False,
            issuer_corporation=self.corporation,
            issuer=self.character,
            reward=50000000,
            start_location=self.jita,
            status=Contract.STATUS_OUTSTANDING,
            volume=50000,
            pricing=self.pricing,
        )

    def test_str(self):
        expected = "1: Jita -> Amamake"
        self.assertEqual(str(self.contract), expected)

    def test_repr(self):
        excepted = "Contract(contract_id=1, start_location=Jita, end_location=Amamake)"
        self.assertEqual(repr(self.contract), excepted)

    def test_hours_issued_2_completed(self):
        self.contract.date_completed = self.contract.date_issued + timedelta(hours=9)
        self.assertEqual(self.contract.hours_issued_2_completed, 9)
        self.contract.date_completed = None
        self.assertIsNone(self.contract.hours_issued_2_completed)

    def test_date_latest(self):
        # initial contract only had date_issued
        self.assertEqual(self.contract.date_issued, self.contract.date_latest)

        # adding date_accepted to contract
        self.contract.date_accepted = self.contract.date_issued + timedelta(days=1)
        self.assertEqual(self.contract.date_accepted, self.contract.date_latest)

        # adding date_completed to contract
        self.contract.date_completed = self.contract.date_accepted + timedelta(days=1)
        self.assertEqual(self.contract.date_completed, self.contract.date_latest)

    @patch(MODULE_PATH + ".FREIGHT_HOURS_UNTIL_STALE_STATUS", 24)
    def test_has_stale_status(self):
        # initial contract only had date_issued
        # date_issued is now
        self.assertFalse(self.contract.has_stale_status)

        # date_issued is 30 hours ago
        self.contract.date_issued = self.contract.date_issued - timedelta(hours=30)
        self.assertTrue(self.contract.has_stale_status)

    def test_acceptor_name(self):

        contract = self.contract
        self.assertIsNone(contract.acceptor_name)

        contract.acceptor_corporation = self.corporation
        self.assertEqual(contract.acceptor_name, self.corporation.corporation_name)

        contract.acceptor = self.character
        self.assertEqual(contract.acceptor_name, self.character.character_name)

    def test_get_issues_list(self):
        self.assertListEqual(self.contract.get_issue_list(), [])
        self.contract.issues = '["one", "two"]'
        self.assertListEqual(self.contract.get_issue_list(), ["one", "two"])

    def test_generate_embed_w_pricing(self):
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)
        self.assertEqual(x.color, Contract.EMBED_COLOR_PASSED)

    def test_generate_embed_w_pricing_issues(self):
        self.contract.issues = ["we have issues"]
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)
        self.assertEqual(x.color, Contract.EMBED_COLOR_FAILED)

    def test_generate_embed_wo_pricing(self):
        self.contract.pricing = None
        x = self.contract._generate_embed()
        self.assertIsInstance(x, Embed)


@patch(MODULE_PATH + ".Webhook.execute", spec=True)
class TestContractSendPilotNotification(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, _ = create_contract_handler_w_contracts()
        cls.contract = Contract.objects.get(contract_id=149409005)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", None)
    def test_aborts_without_webhook_url(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_DISABLE_BRANDING", False)
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_MENTIONS", None)
    def test_with_branding_and_wo_mentions(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_DISABLE_BRANDING", True)
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_MENTIONS", None)
    def test_wo_branding_and_wo_mentions(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_DISABLE_BRANDING", True)
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_MENTIONS", "@here")
    def test_with_branding_and_with_mentions(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_DISABLE_BRANDING", True)
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_MENTIONS", True)
    def test_wo_branding_and_with_mentions(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_WEBHOOK_URL", "url")
    def test_log_error_from_execute(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = False
        mock_webhook_execute.return_value.status_code = 404
        self.contract.send_pilot_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)


@patch(MODULE_PATH + ".Webhook.execute", spec=True)
class TestContractSendCustomerNotification(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler, cls.user = create_contract_handler_w_contracts()
        cls.character = cls.user.profile.main_character
        cls.corporation = cls.character.corporation
        cls.contract_1 = Contract.objects.get(contract_id=149409005)
        cls.contract_2 = Contract.objects.get(contract_id=149409019)
        cls.contract_3 = Contract.objects.get(contract_id=149409118)
        cls.jita = Location.objects.get(id=60003760)
        cls.amamake = Location.objects.get(id=1022167642188)
        cls.amarr = Location.objects.get(id=60008494)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_outstanding(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_in_progress(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract_2.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_finished(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract_3.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_failed(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        my_contract = Contract.objects.create(
            handler=self.handler,
            contract_id=9999,
            collateral=0,
            date_issued=now(),
            date_expired=now() + timedelta(days=5),
            days_to_complete=3,
            end_location=self.amamake,
            for_corporation=False,
            issuer_corporation=self.corporation,
            issuer=self.character,
            reward=50000000,
            start_location=self.jita,
            status=Contract.STATUS_FAILED,
            volume=50000,
        )
        my_contract.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None)
    def test_aborts_without_webhook_url(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".app_labels")
    def test_aborts_without_discord(self, mock_app_labels, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        mock_app_labels.return_value = []
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".User.objects")
    def test_aborts_without_issuer(self, mock_objects, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        mock_objects.filter.return_value.first.return_value = None
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    @patch(MODULE_PATH + ".DiscordUser.objects")
    def test_aborts_without_Discord_user(self, mock_objects, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        mock_objects.get.side_effect = DiscordUser.DoesNotExist
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 0)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_DISABLE_BRANDING", True)
    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_wo_branding(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_log_error_from_execute(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = False
        mock_webhook_execute.return_value.status_code = 404
        self.contract_1.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)

    @patch(MODULE_PATH + ".FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", "url")
    def test_can_send_without_acceptor(self, mock_webhook_execute):
        mock_webhook_execute.return_value.status_ok = True
        my_contract = Contract.objects.create(
            handler=self.handler,
            contract_id=9999,
            collateral=0,
            date_issued=now(),
            date_expired=now() + timedelta(days=5),
            days_to_complete=3,
            end_location=self.amamake,
            for_corporation=False,
            issuer_corporation=self.corporation,
            issuer=self.character,
            reward=50000000,
            start_location=self.jita,
            status=Contract.STATUS_IN_PROGRESS,
            volume=50000,
        )
        my_contract.send_customer_notification()
        self.assertEqual(mock_webhook_execute.call_count, 1)


class TestLocation(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.jita, cls.amamake, _ = create_locations()

    def test_str(self):
        self.assertEqual(
            str(self.jita.name), "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
        )

    def test_repr(self):
        expected = (
            "Location(pk={}, name='Amamake - 3 Time Nearly AT " "Winners')"
        ).format(self.amamake.pk)
        self.assertEqual(repr(self.amamake), expected)

    def test_category(self):
        self.assertEqual(self.jita.category, Location.CATEGORY_STATION_ID)

    def test_solar_system_name_station(self):
        self.assertEqual(self.jita.solar_system_name, "Jita")

    def test_solar_system_name_structure(self):
        self.assertEqual(self.amamake.solar_system_name, "Amamake")

    def test_location_name_station(self):
        self.assertEqual(self.jita.location_name, "Caldari Navy Assembly Plant")

    def test_location_name_structure(self):
        self.assertEqual(self.amamake.location_name, "3 Time Nearly AT Winners")


class TestContractHandler(NoSocketsTestCase):
    def setUp(self):
        for character in characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character["corporation_id"],
                defaults={
                    "corporation_name": character["corporation_name"],
                    "corporation_ticker": character["corporation_ticker"],
                    "member_count": 42,
                },
            )

        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)
        self.corporation = EveCorporationInfo.objects.get(
            corporation_id=self.character.corporation_id
        )
        self.organization = EveEntity.objects.create(
            id=self.character.alliance_id,
            category=EveEntity.CATEGORY_ALLIANCE,
            name=self.character.alliance_name,
        )
        self.user = User.objects.create_user(
            self.character.character_name, "abc@example.com", "password"
        )
        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character, owner_hash="x1", user=self.user
        )
        self.handler = ContractHandler.objects.create(
            organization=self.organization, character=self.main_ownership
        )

    def test_str(self):
        self.assertEqual(str(self.handler), "Justice League")

    def test_repr(self):
        expected = "ContractHandler(pk={}, organization='Justice League')".format(
            self.handler.pk
        )
        self.assertEqual(repr(self.handler), expected)

    def test_operation_mode_friendly(self):
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_ALLIANCE
        self.assertEqual(self.handler.operation_mode_friendly, "My Alliance")
        self.handler.operation_mode = "undefined operation mode"
        with self.assertRaises(ValueError):
            self.handler.operation_mode_friendly

    def test_get_availability_text_for_contracts(self):
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_ALLIANCE
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            "Private (Justice League) [My Alliance]",
        )
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_MY_CORPORATION
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            "Private (Justice League) [My Corporation]",
        )
        self.handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_PUBLIC
        self.assertEqual(
            self.handler.get_availability_text_for_contracts(),
            "Private (Justice League) ",
        )

    @patch(MODULE_PATH + ".FREIGHT_CONTRACT_SYNC_GRACE_MINUTES", 30)
    def test_is_sync_ok(self):
        # no errors and recent sync
        self.handler.last_error = ContractHandler.ERROR_NONE
        self.handler.last_sync = now()
        self.assertTrue(self.handler.is_sync_ok)

        # no errors and sync within grace period
        self.handler.last_error = ContractHandler.ERROR_NONE
        self.handler.last_sync = now() - timedelta(minutes=29)
        self.assertTrue(self.handler.is_sync_ok)

        # recent sync error
        self.handler.last_error = ContractHandler.ERROR_INSUFFICIENT_PERMISSIONS
        self.handler.last_sync = now()
        self.assertFalse(self.handler.is_sync_ok)

        # no error, but no sync within grace period
        self.handler.last_error = ContractHandler.ERROR_NONE
        self.handler.last_sync = now() - timedelta(minutes=31)
        self.assertFalse(self.handler.is_sync_ok)

    def test_set_sync_status_1(self):
        self.handler.last_error = ContractHandler.ERROR_UNKNOWN
        self.handler.last_sync = None
        self.handler.save()

        self.handler.set_sync_status(ContractHandler.ERROR_TOKEN_EXPIRED)
        self.assertEqual(self.handler.last_error, ContractHandler.ERROR_TOKEN_EXPIRED)
        self.assertGreater(self.handler.last_sync, now() - timedelta(minutes=1))

    def test_set_sync_status_2(self):
        self.handler.last_error = ContractHandler.ERROR_UNKNOWN
        self.handler.last_sync = None
        self.handler.save()

        self.handler.set_sync_status()
        self.assertEqual(self.handler.last_error, ContractHandler.ERROR_NONE)
        self.assertGreater(self.handler.last_sync, now() - timedelta(minutes=1))


class TestContractsSync(NoSocketsTestCase):
    def setUp(self):

        create_entities_from_characters()

        # 1 user
        self.character = EveCharacter.objects.get(character_id=90000001)

        self.alliance = EveEntity.objects.get(id=self.character.alliance_id)
        self.corporation = EveEntity.objects.get(id=self.character.corporation_id)
        self.user = User.objects.create_user(
            self.character.character_name, "abc@example.com", "password"
        )
        self.main_ownership = CharacterOwnership.objects.create(
            character=self.character, owner_hash="x1", user=self.user
        )
        create_locations()

    # identify wrong operation mode
    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_CORPORATION)
    def test_abort_on_wrong_operation_mode(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
        )
        self.assertFalse(handler.update_contracts_esi())
        handler.refresh_from_db()
        self.assertEqual(
            handler.last_error, ContractHandler.ERROR_OPERATION_MODE_MISMATCH
        )

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    def test_abort_when_no_sync_char(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        self.assertFalse(handler.update_contracts_esi())
        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NO_CHARACTER)

    # test expired token
    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".Token")
    def test_abort_when_token_expired(self, mock_Token):
        mock_Token.objects.filter.side_effect = TokenExpiredError()
        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )

        # run manager sync
        self.assertFalse(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_TOKEN_EXPIRED)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".Token")
    def test_abort_when_token_invalid(self, mock_Token):
        mock_Token.objects.filter.side_effect = TokenInvalidError()
        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )

        self.assertFalse(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_TOKEN_INVALID)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".Token")
    def test_abort_when_no_token_exists(self, mock_Token):
        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = (
            None
        )

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        self.assertFalse(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_TOKEN_INVALID)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".Contract.objects.update_or_create_from_dict")
    @patch(MODULE_PATH + ".Token")
    @patch("freight.helpers.esi_fetch._esi_client")
    def test_abort_when_exception_occurs_during_contract_creation(
        self,
        mock_esi_client,
        mock_Token,
        mock_Contracts_objects_update_or_create_from_dict,
    ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            mock_response = Mock()
            mock_response.headers = {"x-pages": pages_count}
            return [contracts_data[start:stop], mock_response]

        def func_Contracts_objects_update_or_create_from_dict(handler, contract, token):
            raise RuntimeError("Test exception")

        mock_Contracts_objects_update_or_create_from_dict.side_effect = (
            func_Contracts_objects_update_or_create_from_dict
        )

        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page
        mock_esi_client.return_value.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )

        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )

        # run manager sync
        self.assertTrue(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_UNKNOWN)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".Token")
    @patch("freight.helpers.esi_fetch._esi_client")
    def test_can_sync_contracts_for_my_alliance(self, mock_esi_client, mock_Token):
        current_page = 0

        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            nonlocal current_page
            page_size = 2
            current_page += 1
            start = (current_page - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            mock_response = Mock()
            mock_response.headers = {"x-pages": pages_count}
            return [contracts_data[start:stop], mock_response]

        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page
        mock_esi_client.return_value.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )

        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )

        self.assertTrue(handler.update_contracts_esi())

        # no errors reported
        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NONE)

        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x["contract_id"]
            for x in Contract.objects.filter(
                status__exact=Contract.STATUS_OUTSTANDING
            ).values("contract_id")
        ]
        self.assertCountEqual(
            contract_ids, [149409005, 149409014, 149409006, 149409015]
        )

        # 2nd run should not update anything, but reset last_sync
        current_page = 0
        Contract.objects.all().delete()
        handler.last_sync = None
        handler.last_error = ContractHandler.ERROR_UNKNOWN
        handler.save()
        self.assertTrue(handler.update_contracts_esi())
        self.assertEqual(Contract.objects.count(), 0)
        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NONE)
        self.assertIsNotNone(handler.last_sync)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_CORPORATION)
    @patch(MODULE_PATH + ".notify")
    @patch(MODULE_PATH + ".Token")
    @patch("freight.helpers.esi_fetch._esi_client")
    def test_sync_contracts_for_my_corporation_and_ignore_notify_exception(
        self, mock_esi_client, mock_Token, mock_notify
    ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            mock_response = Mock()
            mock_response.headers = {"x-pages": pages_count}
            return [contracts_data[start:stop], mock_response]

        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page
        mock_esi_client.return_value.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )

        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )

        mock_notify.side_effect = RuntimeError

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_CORPORATION,
        )

        # run manager sync
        self.assertTrue(handler.update_contracts_esi(user=self.user))

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NONE)

        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x["contract_id"]
            for x in Contract.objects.filter(
                status__exact=Contract.STATUS_OUTSTANDING
            ).values("contract_id")
        ]
        self.assertCountEqual(
            contract_ids, [149409016, 149409061, 149409062, 149409063, 149409064,]
        )

        # should have tried to notify user
        self.assertTrue(mock_notify.called)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE)
    @patch(MODULE_PATH + ".notify")
    @patch(MODULE_PATH + ".Token")
    @patch("freight.helpers.esi_fetch._esi_client")
    def test_sync_contracts_for_corp_in_alliance_and_report_to_user(
        self, mock_esi_client, mock_Token, mock_notify
    ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            mock_response = Mock()
            mock_response.headers = {"x-pages": pages_count}
            return [contracts_data[start:stop], mock_response]

        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page
        mock_esi_client.return_value.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )

        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
        )

        # run manager sync
        self.assertTrue(handler.update_contracts_esi(user=self.user))

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NONE)

        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x["contract_id"]
            for x in Contract.objects.filter(
                status__exact=Contract.STATUS_OUTSTANDING
            ).values("contract_id")
        ]
        self.assertCountEqual(
            contract_ids,
            [149409016, 149409017, 149409061, 149409062, 149409063, 149409064,],
        )

        # should have notified user with success
        self.assertTrue(mock_notify.called)
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["level"], "success")

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_CORP_PUBLIC)
    @patch(MODULE_PATH + ".Token")
    @patch(
        "freight.managers.EveCorporationInfo.objects.create_corporation",
        side_effect=ObjectNotFound(9999999, "corporation"),
    )
    @patch(
        "freight.managers.EveCharacter.objects.create_character",
        side_effect=ObjectNotFound(9999999, "character"),
    )
    @patch("freight.helpers.esi_fetch._esi_client")
    def test_can_sync_contracts_for_corp_public(
        self,
        mock_esi_client,
        mock_EveCharacter_objects_create_character,
        mock_EveCorporationInfo_objects_create_corporation,
        mock_Token,
    ):
        # create mocks
        def get_contracts_page(*args, **kwargs):
            """returns single page for operation.result(), first with header"""
            page_size = 2
            mock_calls_count = len(mock_operation.mock_calls)
            start = (mock_calls_count - 1) * page_size
            stop = start + page_size
            pages_count = int(math.ceil(len(contracts_data) / page_size))
            mock_response = Mock()
            mock_response.headers = {"x-pages": pages_count}
            return [contracts_data[start:stop], mock_response]

        mock_operation = Mock()
        mock_operation.result.side_effect = get_contracts_page
        mock_esi_client.return_value.Contracts.get_corporations_corporation_id_contracts = Mock(
            return_value=mock_operation
        )

        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )

        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.corporation,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_CORP_PUBLIC,
        )

        # run manager sync
        self.assertTrue(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_NONE)

        # should have tried to fetch contracts
        self.assertEqual(mock_operation.result.call_count, 9)

        # should only contain the right contracts
        contract_ids = [
            x["contract_id"]
            for x in Contract.objects.filter(
                status__exact=Contract.STATUS_OUTSTANDING
            ).values("contract_id")
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
                149409018,
            ],
        )

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    @patch(MODULE_PATH + ".esi_fetch")
    @patch(MODULE_PATH + ".ContractHandler.token")
    def test_abort_on_general_exception(self, mock_token, mock_fetch):
        mock_fetch.side_effect = RuntimeError
        AuthUtils.add_permission_to_user_by_name(
            "freight.setup_contract_handler", self.user
        )
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            character=self.main_ownership,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        )
        self.assertFalse(handler.update_contracts_esi())

        handler.refresh_from_db()
        self.assertEqual(handler.last_error, ContractHandler.ERROR_UNKNOWN)

    @patch(PATCH_FREIGHT_OPERATION_MODE, FREIGHT_OPERATION_MODE_MY_ALLIANCE)
    def test_operation_mode_friendly(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
        )
        self.assertEqual(handler.operation_mode_friendly, FREIGHT_OPERATION_MODES[0][1])

        handler.operation_mode = FREIGHT_OPERATION_MODE_MY_CORPORATION
        self.assertEqual(handler.operation_mode_friendly, FREIGHT_OPERATION_MODES[1][1])

        handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE
        self.assertEqual(handler.operation_mode_friendly, FREIGHT_OPERATION_MODES[2][1])

        handler.operation_mode = FREIGHT_OPERATION_MODE_CORP_PUBLIC
        self.assertEqual(handler.operation_mode_friendly, FREIGHT_OPERATION_MODES[3][1])

    def test_last_error_message_friendly(self):
        handler = ContractHandler.objects.create(
            organization=self.alliance,
            operation_mode=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
            character=self.main_ownership,
            last_error=ContractHandler.ERROR_UNKNOWN,
        )
        self.assertEqual(
            handler.last_error_message_friendly, ContractHandler.ERRORS_LIST[7][1]
        )


class TestEveEntity(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_entities_from_characters()
        cls.alliance = EveEntity.objects.get(id=93000001)
        cls.corporation = EveEntity.objects.get(id=92000001)
        cls.character = EveEntity.objects.get(id=90000001)

    def test_str(self):
        self.assertEqual(str(self.character), "Bruce Wayne")

    def test_repr(self):
        expected = (
            "EveEntity(id={}, " "category='character', " "name='Bruce Wayne')"
        ).format(self.character.id)
        self.assertEqual(repr(self.character), expected)

    def test_is_alliance(self):
        self.assertFalse(self.character.is_alliance)
        self.assertFalse(self.corporation.is_alliance)
        self.assertTrue(self.alliance.is_alliance)

    def test_is_corporation(self):
        self.assertFalse(self.character.is_corporation)
        self.assertTrue(self.corporation.is_corporation)
        self.assertFalse(self.alliance.is_corporation)

    def test_is_character(self):
        self.assertTrue(self.character.is_character)
        self.assertFalse(self.corporation.is_character)
        self.assertFalse(self.alliance.is_character)

    def test_avatar_url_alliance(self):
        expected = "https://images.evetech.net/alliances/93000001/logo?size=128"
        self.assertEqual(self.alliance.avatar_url, expected)

    def test_avatar_url_corporation(self):
        expected = "https://images.evetech.net/corporations/92000001/logo?size=128"
        self.assertEqual(self.corporation.avatar_url, expected)

    def test_avatar_url_character(self):
        expected = "https://images.evetech.net/characters/90000001/portrait?size=128"
        self.assertEqual(self.character.avatar_url, expected)

    def test_get_category_for_operation_mode_1(self):
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


class TestContractCustomerNotification(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for character in characters_data:
            EveCharacter.objects.create(**character)
            EveCorporationInfo.objects.get_or_create(
                corporation_id=character["corporation_id"],
                defaults={
                    "corporation_name": character["corporation_name"],
                    "corporation_ticker": character["corporation_ticker"],
                    "member_count": 42,
                },
            )

        # 1 user
        cls.character = EveCharacter.objects.get(character_id=90000001)
        cls.corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.character.corporation_id
        )
        cls.organization = EveEntity.objects.create(
            id=cls.character.alliance_id,
            category=EveEntity.CATEGORY_ALLIANCE,
            name=cls.character.alliance_name,
        )
        cls.user = User.objects.create_user(
            cls.character.character_name, "abc@example.com", "password"
        )
        cls.main_ownership = CharacterOwnership.objects.create(
            character=cls.character, owner_hash="x1", user=cls.user
        )
        # Locations
        cls.location_1 = Location.objects.create(
            id=60003760,
            name="Jita IV - Moon 4 - Caldari Navy Assembly Plant",
            solar_system_id=30000142,
            type_id=52678,
            category_id=3,
        )
        cls.location_2 = Location.objects.create(
            id=1022167642188,
            name="Amamake - 3 Time Nearly AT Winners",
            solar_system_id=30002537,
            type_id=35834,
            category_id=65,
        )
        cls.handler = ContractHandler.objects.create(
            organization=cls.organization, character=cls.main_ownership
        )

    def setUp(self):
        # create contracts
        with DisconnectPricingSaveHandler():
            self.pricing = Pricing.objects.create(
                start_location=self.location_1,
                end_location=self.location_2,
                price_base=500000000,
            )
        self.contract = Contract.objects.create(
            handler=self.handler,
            contract_id=1,
            collateral=0,
            date_issued=now(),
            date_expired=now() + timedelta(days=5),
            days_to_complete=3,
            end_location=self.location_2,
            for_corporation=False,
            issuer_corporation=self.corporation,
            issuer=self.character,
            reward=50000000,
            start_location=self.location_1,
            status=Contract.STATUS_OUTSTANDING,
            volume=50000,
            pricing=self.pricing,
        )
        self.notification = ContractCustomerNotification.objects.create(
            contract=self.contract,
            status=Contract.STATUS_IN_PROGRESS,
            date_notified=now(),
        )

    def test_str(self):
        expected = "{} - in_progress".format(self.contract.contract_id)
        self.assertEqual(str(self.notification), expected)

    def test_repr(self):
        expected = (
            "ContractCustomerNotification(pk={}, contract_id={}, " "status=in_progress)"
        ).format(self.notification.pk, self.notification.contract.contract_id)
        self.assertEqual(repr(self.notification), expected)
