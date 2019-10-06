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
        validators=[            
            MinValueValidator(1)
        ]
    )
    collateral = forms.IntegerField(
        help_text='Collaterial in M ISK, must be roughly equal to the est. '\
            + 'value of your cargo',
        validators=[            
            MinValueValidator(0)
        ]
    )

    def clean(self):        
        errors = self.cleaned_data['pricing'].get_contract_pricing_errors(
            self.cleaned_data['volume'] * 1000,
            self.cleaned_data['collateral'] * 1000000                
        )
        
        if errors:
            raise ValidationError(
                'Input errors: ' + ", ".join(errors)
            )
    

class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label='Location ID',
        help_text='Eve Online ID for a station or an Upwell structure'
    )    

