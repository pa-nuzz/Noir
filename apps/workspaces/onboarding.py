from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import Workspace


class WorkspaceOnboarding(models.Model):
    STEPS = [
        ('connect_sender', 'Connect a Sender'),
        ('import_contacts', 'Import Contacts'),
        ('create_campaign', 'Create First Campaign'),
        ('connect_social', 'Connect Social Account'),
    ]

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name='onboarding')
    connect_sender = models.BooleanField(default=False)
    connect_sender_skipped = models.BooleanField(default=False)
    import_contacts = models.BooleanField(default=False)
    import_contacts_skipped = models.BooleanField(default=False)
    create_campaign = models.BooleanField(default=False)
    create_campaign_skipped = models.BooleanField(default=False)
    connect_social = models.BooleanField(default=False)
    connect_social_skipped = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Workspace onboarding'
        verbose_name_plural = 'Workspace onboarding'

    def __str__(self):
        return f'Onboarding: {self.workspace.name}'

    @property
    def completed_steps(self):
        return sum(1 for step, _ in self.STEPS if getattr(self, step, False))

    @property
    def total_steps(self):
        return len(self.STEPS)

    @property
    def progress_pct(self):
        return int((self.completed_steps / self.total_steps) * 100) if self.total_steps else 100

    @property
    def is_complete(self):
        return self.completed_steps >= self.total_steps

    @property
    def next_step(self):
        for step, label in self.STEPS:
            if not getattr(self, step, False) and not getattr(self, f'{step}_skipped', False):
                return step, label
        return None, None

    def mark_done(self, step_name):
        if step_name in dict(self.STEPS):
            setattr(self, step_name, True)
            self.save(update_fields=[step_name, 'updated_at'])

    def skip(self, step_name):
        if step_name in dict(self.STEPS):
            setattr(self, f'{step_name}_skipped', True)
            self.save(update_fields=[f'{step_name}_skipped', 'updated_at'])


def get_or_create_onboarding(workspace):
    obj, _ = WorkspaceOnboarding.objects.get_or_create(workspace=workspace)
    return obj
