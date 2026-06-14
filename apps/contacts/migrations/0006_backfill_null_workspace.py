from django.db import migrations


def backfill_workspace(apps, schema_editor):
    ContactList = apps.get_model('contacts', 'ContactList')
    ContactTag = apps.get_model('contacts', 'ContactTag')
    ContactCustomField = apps.get_model('contacts', 'ContactCustomField')
    ContactSegment = apps.get_model('contacts', 'ContactSegment')
    WorkspaceMembership = apps.get_model('workspaces', 'WorkspaceMembership')

    models_to_backfill = [
        (ContactList, 'contact_lists'),
        (ContactTag, 'contact_tags'),
        (ContactCustomField, 'custom_fields'),
        (ContactSegment, 'contact_segments'),
    ]

    for model, related_name in models_to_backfill:
        for obj in model.objects.filter(workspace__isnull=True).select_related('user').iterator():
            user = obj.user
            memberships = list(
                WorkspaceMembership.objects.filter(user=user)
                .select_related('workspace')[:2]
            )
            if len(memberships) == 1:
                obj.workspace = memberships[0].workspace
                obj.save(update_fields=['workspace'])


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0005_unique_constraints_and_workspace_scoping"),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_workspace, migrations.RunPython.noop),
    ]
