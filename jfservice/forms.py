from django import forms
from .models import Pricing

class CalculatorForm(forms.Form):         
    pricing = forms.ModelChoiceField(queryset=Pricing.objects.filter(active__exact=True))
    volume = forms.IntegerField()
    collateral = forms.IntegerField()
    