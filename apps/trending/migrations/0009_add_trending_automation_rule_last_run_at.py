from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trending", "0008_fix_audit_defaults"),
        ("trending", "0007_add_trending_automation_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="trendingautomationrule",
            name="last_run_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
