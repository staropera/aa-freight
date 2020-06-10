import math

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from .models import Pricing


class CalculatorForm(forms.Form):
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects.filter(is_active=True).order_by(
            "start_location__name", "end_location__name"
        ),
        label="Route",
        help_text="Pick a route for your courier contract",
        empty_label=None,
    )
    volume = forms.IntegerField(
        help_text="Est. volume of your cargo in m3",
        required=False,
        validators=[MinValueValidator(0)],
    )
    collateral = forms.IntegerField(
        help_text=(
            "Collaterial in ISK, must be roughly equal to the est. "
            "value of your cargo"
        ),
        required=False,
        validators=[MinValueValidator(0)],
    )

    def clean(self):
        pricing = self.cleaned_data["pricing"]
        issue_prefix = "⚠ Issues:"

        if pricing.requires_volume() and self.cleaned_data["volume"] is None:
            raise ValidationError("{} volume is required".format(issue_prefix))

        if pricing.requires_collateral() and self.cleaned_data["collateral"] is None:
            raise ValidationError("{} collateral is required".format(issue_prefix))

        volume = self.cleaned_data["volume"]
        collateral = self.cleaned_data["collateral"]
        issues = pricing.get_contract_price_check_issues(volume, collateral)

        if issues:
            raise ValidationError("{} {}".format(issue_prefix, ", ".join(issues)))

    def get_calculated_data(self, pricing: object) -> tuple:
        if self.is_valid():
            if self.cleaned_data["volume"]:
                volume = int(self.cleaned_data["volume"])
            else:
                volume = 0
            if self.cleaned_data["collateral"]:
                collateral = int(self.cleaned_data["collateral"])
            else:
                collateral = 0
            price = (
                math.ceil(pricing.get_calculated_price(volume, collateral) / 1000000)
                * 1000000
            )

        else:
            volume = None
            collateral = None
            price = None

        return volume, collateral, price


class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label="Location ID",
        help_text="Eve Online ID for a station or an Upwell structure",
    )
