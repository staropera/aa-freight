from django import template

register = template.Library()

@register.filter
def to_millions(value):   
    """converts the value into millions""" 
    return value / 1000000

@register.filter
def to_thousands(value):   
    """converts the value into thousands""" 
    return value / 1000