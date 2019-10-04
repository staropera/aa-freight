from django import template

register = template.Library()

@register.filter
def power10(value, k = 0):   
    """converts the value to a power of 10 representation""" 
    if value:            
        return value / (10 ** int(k))
    else:
        return None

@register.filter
def formatnumber(value, p = 1):
    """return a formated number with thousands seperators""" 
    if value:
        return '{:,.{}f}'.format(float(value), int(p))
    else:
        return None