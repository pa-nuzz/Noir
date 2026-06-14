from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0004_contact_contacts_co_contact_434e63_idx_and_more"),
    ]

    operations = [
        # Remove old unique_together constraints
        migrations.AlterUniqueTogether(
            name="contacttag",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="contactcustomfield",
            unique_together=set(),
        ),
        # Add new conditional UniqueConstraints for ContactTag
        migrations.AddConstraint(
            model_name="contacttag",
            constraint=models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(workspace__isnull=False),
                name="unique_tag_per_workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="contacttag",
            constraint=models.UniqueConstraint(
                fields=["user", "name"],
                condition=Q(workspace__isnull=True),
                name="unique_tag_per_user",
            ),
        ),
        # Add new conditional UniqueConstraints for ContactCustomField
        migrations.AddConstraint(
            model_name="contactcustomfield",
            constraint=models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(workspace__isnull=False),
                name="unique_custom_field_per_workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="contactcustomfield",
            constraint=models.UniqueConstraint(
                fields=["user", "name"],
                condition=Q(workspace__isnull=True),
                name="unique_custom_field_per_user",
            ),
        ),
    ]
