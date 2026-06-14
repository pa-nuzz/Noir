from django import template

register = template.Library()


@register.filter
def dictget(d, key):
    """Get a value from a dictionary or list by key/index. Usage: mydict|dictget:key"""
    if d is None:
        return None
    if hasattr(d, 'get'):
        return d.get(key)
    try:
        return d[key]
    except (IndexError, KeyError, TypeError):
        return None


@register.simple_tag(takes_context=True)
def can_read(context, module):
    perms = context.get('workspace_permissions', None)
    if perms is None:
        return True
    return bool(perms.get(module, {}).get('read', False))


@register.simple_tag(takes_context=True)
def can_create(context, module):
    perms = context.get('workspace_permissions', None)
    if perms is None:
        return True
    return bool(perms.get(module, {}).get('create', False))


@register.simple_tag(takes_context=True)
def can_edit(context, module):
    perms = context.get('workspace_permissions', None)
    if perms is None:
        return True
    return bool(perms.get(module, {}).get('edit', False))


@register.simple_tag(takes_context=True)
def can_delete(context, module):
    perms = context.get('workspace_permissions', None)
    if perms is None:
        return True
    return bool(perms.get(module, {}).get('delete', False))


@register.simple_tag(takes_context=True)
def can_manage_workspace(context):
    membership = context.get('active_membership', None)
    if membership is None:
        return False
    return membership.role in ('owner', 'admin')