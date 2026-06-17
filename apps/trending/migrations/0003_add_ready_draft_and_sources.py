from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


TOPICS = [
    {'name': 'Productivity & Tools', 'slug': 'productivity-tools', 'description': 'Productivity apps, project management, collaboration tools, and workflow automation', 'icon': '⚡', 'color': '#F59E0B', 'keywords': ['productivity', 'tools', 'project management', 'collaboration', 'workflow', 'automation', 'Notion', 'Linear', 'Slack', 'Asana', 'Jira', 'Trello']},
    {'name': 'Science & Research', 'slug': 'science-research', 'description': 'Scientific discoveries, research papers, physics, biology, and breakthrough studies', 'icon': '🔬', 'color': '#14B8A6', 'keywords': ['science', 'research', 'physics', 'biology', 'chemistry', 'study', 'discovery', 'Nature', 'Science', 'paper', 'scientist', 'lab']},
    {'name': 'Gaming', 'slug': 'gaming', 'description': 'Game development, esports, gaming industry news, and game design', 'icon': '🎮', 'color': '#8B5CF6', 'keywords': ['gaming', 'game', 'esports', 'Unity', 'Unreal', 'Steam', 'console', 'PC gaming', 'mobile game', 'indie game']},
]

NEW_SOURCES = [
    {'name': 'Y Combinator', 'source_type': 'rss', 'url': 'https://news.ycombinator.com/rss', 'poll_interval_hours': 6},
    {'name': 'MIT Technology Review', 'source_type': 'web', 'url': 'https://www.technologyreview.com/', 'poll_interval_hours': 6, 'config_json': {'content_pattern': '<h2[^>]*>(.*?)</h2>', 'max_items': 20}},
    {'name': 'Ars Technica', 'source_type': 'rss', 'url': 'https://feeds.arstechnica.com/arstechnica/index', 'poll_interval_hours': 6},
    {'name': 'The Verge', 'source_type': 'rss', 'url': 'https://www.theverge.com/rss/index.xml', 'poll_interval_hours': 6},
    {'name': 'Wired', 'source_type': 'rss', 'url': 'https://www.wired.com/feed/rss', 'poll_interval_hours': 6},
    {'name': 'ScienceDaily', 'source_type': 'rss', 'url': 'https://www.sciencedaily.com/rss/all.xml', 'poll_interval_hours': 6},
    {'name': 'Smashing Magazine', 'source_type': 'rss', 'url': 'https://www.smashingmagazine.com/feed/', 'poll_interval_hours': 6},
    {'name': 'Stack Overflow Blog', 'source_type': 'rss', 'url': 'https://stackoverflow.blog/feed/', 'poll_interval_hours': 6},
    {'name': 'Product Hunt', 'source_type': 'web', 'url': 'https://www.producthunt.com/', 'poll_interval_hours': 6, 'config_json': {'content_pattern': '<a[^>]*class="[^"]*post-name[^"]*"[^>]*>(.*?)</a>', 'max_items': 20}},
]


def seed_new_data(apps, schema_editor):
    Topic = apps.get_model('trending', 'Topic')
    ContentSource = apps.get_model('trending', 'ContentSource')

    for t in TOPICS:
        Topic.objects.get_or_create(
            slug=t['slug'],
            defaults=t,
        )

    for s in NEW_SOURCES:
        ContentSource.objects.get_or_create(
            name=s['name'],
            defaults=s,
        )


def reverse_seed(apps, schema_editor):
    Topic = apps.get_model('trending', 'Topic')
    ContentSource = apps.get_model('trending', 'ContentSource')
    Topic.objects.filter(slug__in=[t['slug'] for t in TOPICS]).delete()
    ContentSource.objects.filter(name__in=[s['name'] for s in NEW_SOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('trending', '0002_seed_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReadyDraftItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('scheduled', 'Scheduled'), ('published', 'Published')], default='draft', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('feed_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ready_drafts', to='trending.feeditem')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ready_drafts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('user', 'feed_item')},
            },
        ),
        migrations.RunPython(seed_new_data, reverse_seed),
    ]
