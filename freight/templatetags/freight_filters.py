from django import template

register = template.Library()


@register.filter
def power10(value, k=0):
    """converts the value to a power of 10 representation"""
    try:
        return float(value) / (10 ** int(k))
    except (ValueError, TypeError):
        return None


@register.filter
def formatnumber(value, p=1):
    """return a formated number with thousands seperators"""
    try:
        return "{:,.{}f}".format(float(value), int(p))
    except (ValueError, TypeError):
        return None
