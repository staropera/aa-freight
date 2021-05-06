from django.urls import reverse
from django_webtest import WebTest

from allianceauth.tests.auth_utils import AuthUtils

from ..models import Contract, Location, Pricing
from . import DisconnectPricingSaveHandler
from .testdata import create_contract_handler_w_contracts


class TestCalculatorWeb(WebTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.user = create_contract_handler_w_contracts()
        AuthUtils.add_permission_to_user_by_name("freight.use_calculator", cls.user)
        with DisconnectPricingSaveHandler():
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
                days_to_expire=7,
            )
            cls.pricing_2 = Pricing.objects.create(
                start_location=jita, end_location=amarr, price_base=100000000
            )
        Contract.objects.update_pricing()

    def _calculate_price(self, pricing: Pricing, volume=None, collateral=None) -> tuple:
        """Performs a full price query with the calculator

        returns tuple of price_str, form, request
        """
        self.app.set_user(self.user)
        # load page and get our form
        response = self.app.get(reverse("freight:calculator"))
        form = None
        for _, obj in response.forms.items():
            if obj.id == "form_calculator":
                form = obj
        self.assertIsNotNone(form)

        # enter these values into form
        form["pricing"] = pricing.pk
        if volume:
            form["volume"] = volume
        if collateral:
            form["collateral"] = collateral

        # submit form and get response
        response = form.submit()
        form = None
        for _, obj in response.forms.items():
            if obj.id == "form_calculator":
                form = obj
        self.assertIsNotNone(form)

        # extract the price string
        price_str = response.html.find(id="text_price_2").string.strip()
        return price_str, form, response

    def test_can_calculate_pricing_1(self):
        price_str, _, _ = self._calculate_price(self.pricing_1, 50000, 2000000000)
        expected = "98,000,000 ISK"
        self.assertEqual(price_str, expected)

    def test_can_calculate_pricing_2(self):
        price_str, _, _ = self._calculate_price(self.pricing_2)
        expected = "100,000,000 ISK"
        self.assertEqual(price_str, expected)

    def test_aborts_on_missing_collateral(self):
        price_str, form, _ = self._calculate_price(self.pricing_1, 50000)
        expected = "- ISK"
        self.assertEqual(price_str, expected)
        self.assertIn("Issues", form.text)
        self.assertIn("collateral is required", form.text)

    def test_aborts_on_missing_volume(self):
        price_str, form, _ = self._calculate_price(self.pricing_1, None, 500000)
        expected = "- ISK"
        self.assertEqual(price_str, expected)
        self.assertIn("Issues", form.text)
        self.assertIn("volume is required", form.text)

    def test_aborts_on_too_high_volume(self):
        price_str, form, _ = self._calculate_price(self.pricing_1, 400000, 500000)
        expected = "- ISK"
        self.assertEqual(price_str, expected)
        self.assertIn("Issues", form.text)
        self.assertIn("exceeds the maximum allowed volume", form.text)

    def test_aborts_on_too_high_collateral(self):
        price_str, form, _ = self._calculate_price(self.pricing_1, 40000, 6000000000)
        expected = "- ISK"
        self.assertEqual(price_str, expected)
        self.assertIn("Issues", form.text)
        self.assertIn("exceeds the maximum allowed collateral", form.text)
