from django import forms

class CalculatorForm(forms.Form): 
    volume = forms.IntegerField()
    collateral = forms.IntegerField()
    