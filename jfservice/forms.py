from django import forms
from .models import Pricing

class CalculatorForm(forms.Form):         
    pricing = forms.ModelChoiceField(
        queryset=Pricing.objects.filter(active__exact=True),
        initial=Pricing.objects.filter(active__exact=True).first(),
        label='Route',
        help_text='Route for this contract'
    )
    volume = forms.IntegerField(
        help_text='Est. volume of your cargo in 1,000x m3'
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
    