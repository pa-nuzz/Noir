from django import template
from .inbox_filters import hash_hue, gravatar_url, sender_logo_url

register = template.Library()

# Register filters from inbox_filters
register.filter('hash_hue', hash_hue)
register.filter('gravatar_url', gravatar_url)
register.filter('sender_logo_url', sender_logo_url)


@register.filter
def div(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
