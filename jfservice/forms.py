from django import forms
from .models import Pricing


class CalculatorForm(forms.Form):         
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects.filter(active__exact=True),
        initial=Pricing.objects.filter(active__exact=True).first(),
        label='Route',
        help_text='Pick the route for your courier contract'
    )
    volume = forms.IntegerField(
        help_text='Est. volume of your cargo in K x m3, e.g. "50" = 50.000 m3'
    )
    collateral = forms.IntegerField(
        help_text='Collaterial in M ISK'
    )

    def clean_volume(self):
        volume = self.cleaned_data['volume']
        if volume <0:
            raise forms.ValidationError('Volume can not be negative')
        else:
            return volume
    

class AddLocationForm(forms.Form):
    location_id = forms.IntegerField(
        label='Location ID',
        help_text='Eve Online ID for a station or an Upwell structure'
    )    

