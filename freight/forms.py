from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from .models import Pricing


class CalculatorForm(forms.Form):             
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects
        .filter(is_active=True)
        .order_by('start_location__name', 'end_location__name'),
        label='Route',
        help_text='Pick a route for your courier contract',
        empty_label=None
    )    
    volume = forms.IntegerField(
        help_text='Est. volume of your cargo in m3',
        required=False,
        validators=[            
            MinValueValidator(0)
        ]
    )
    collateral = forms.IntegerField(
        help_text=(
            'Collaterial in ISK, must be roughly equal to the est. '
            'value of your cargo'
        ),
        required=False,
        validators=[            
            MinValueValidator(0)
        ]
    )

    def clean(self):                
        pricing = self.cleaned_data['pricing']
        issue_prefix = '⚠ Issues:'
        
        if (pricing.requires_volume() 
            and self.cleaned_data['volume'] is None
        ):
            raise ValidationError(
                '{} volume is required'.format(issue_prefix)
            )

        if (pricing.requires_collateral() 
            and self.cleaned_data['collateral'] is None
        ):
            raise ValidationError(
                '{} collateral is required'.format(issue_prefix)
            )        
        
        volume = self.cleaned_data['volume']        
        collateral = self.cleaned_data['collateral']        
        issues = pricing.get_contract_price_check_issues(
            volume,
            collateral
        )
        
        if issues:
            raise ValidationError(                
                '{} {}'.format(issue_prefix, ", ".join(issues))
            )
    

class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label='Location ID',
        help_text='Eve Online ID for a station or an Upwell structure'
    )    
