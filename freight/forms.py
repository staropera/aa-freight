from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import Pricing


class CalculatorForm(forms.Form):             
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects.filter(active__exact=True),
        initial=Pricing.objects.filter(active__exact=True).first(),
        label='Route',
        help_text='Pick a route for your courier contract',
        empty_label=None
    )    
    volume = forms.IntegerField(
        help_text='Est. volume of your cargo in K x m3, e.g. "50" = 50.000 m3',
        required = False,
        validators=[            
            MinValueValidator(0)
        ]
    )
    collateral = forms.IntegerField(
        help_text='Collaterial in M ISK, must be roughly equal to the est. '\
            + 'value of your cargo',
        required = False,
        validators=[            
            MinValueValidator(0)
        ]
    )

    def clean(self):                
        pricing = self.cleaned_data['pricing']
        
        if pricing.requires_volume() and not self.cleaned_data['volume']:
            raise ValidationError(
                'Issues: volume is required'
            )

        if pricing.requires_collateral() and not self.cleaned_data['collateral']:
            raise ValidationError(
                'Issues: collateral is required'
            )
        
        if self.cleaned_data['volume']:
            volume = self.cleaned_data['volume'] * 1000
        else:
            volume = 0
        if self.cleaned_data['collateral']:
            collateral = self.cleaned_data['collateral'] * 1000
        else:
            collateral = 0
        issues = pricing.get_contract_price_check_issues(
            volume,
            collateral
        )
        
        if issues:
            raise ValidationError(
                'Issues: ' + ", ".join(issues)
            )
    

class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label='Location ID',
        help_text='Eve Online ID for a station or an Upwell structure'
    )    

