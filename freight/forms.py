from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import Pricing


class CalculatorForm(forms.Form):             
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects.filter(active__exact=True),
        initial=Pricing.objects.filter(active__exact=True).first(),
        label='Route',
        help_text='Pick an route fitting for your courier contract',
        empty_label=None
    )    
    volume = forms.IntegerField(
        help_text='Est. volume of your cargo in K x m3, e.g. "50" = 50.000 m3',
        validators=[            
            MinValueValidator(1),
            MaxValueValidator(2000),
        ]
    )
    collateral = forms.IntegerField(
        help_text='Collaterial in M ISK',
        validators=[            
            MinValueValidator(0),
            MaxValueValidator(1000000),
        ]
    )
    

class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label='Location ID',
        help_text='Eve Online ID for a station or an Upwell structure'
    )    

