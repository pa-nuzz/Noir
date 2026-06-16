from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('trending', '0004_feeditem_image_url'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ReadyDraftItem',
            new_name='CurrentItem',
        ),
        migrations.AlterField(
            model_name='currentitem',
            name='feed_item',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='currents', to='trending.feeditem'),
        ),
        migrations.AlterField(
            model_name='currentitem',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='currents', to=settings.AUTH_USER_MODEL),
        ),
    ]
