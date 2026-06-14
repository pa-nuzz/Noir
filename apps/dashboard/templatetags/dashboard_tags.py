from django import template
from django.utils import timezone

register = template.Library()

@register.simple_tag(takes_context=True)
def greeting(context):
    local_time = timezone.localtime(timezone.now())
    hour = local_time.hour
    if hour < 12:
        return "Good Morning"
    if hour < 18:
        return "Good Afternoon"
    return "Good Evening"


@register.filter
def split(value, delimiter):
    return value.split(delimiter)


@register.filter
def dictget(value, key):
    try:
        return value.get(key)
    except (AttributeError, TypeError):
        return None
