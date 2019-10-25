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
            MinValueValidator(0)
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
        issues = self.cleaned_data['pricing'].get_contract_price_check_issues(
            self.cleaned_data['volume'] * 1000 if 'volume' in self.cleaned_data else 0,
            self.cleaned_data['collateral'] * 1000000 if 'collateral' in self.cleaned_data else 0
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

