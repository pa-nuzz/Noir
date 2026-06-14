from django.apps import AppConfig


class AutomationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.automations'
    verbose_name = 'Automations (Drip Sequences)'

    def ready(self):
        import apps.automations.signals  # noqa: F401
