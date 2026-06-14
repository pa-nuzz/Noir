from django.db import models
from django.conf import settings
from django.utils import timezone

from core.tenant import TenantManager


class Workflow(models.Model):
    objects = TenantManager()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workflows')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='workflows')
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class WorkflowNode(models.Model):
    NODE_TYPES = [
        ('trigger', 'Trigger'),
        ('delay', 'Delay'),
        ('action', 'Action'),
        ('wait_until_condition', 'Wait Until Condition'),
        ('branch', 'Branch (If/Else)'),
        ('goal', 'Goal (Stop on Conversion)'),
    ]

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='nodes')
    node_id = models.CharField(max_length=64)
    type = models.CharField(max_length=20, choices=NODE_TYPES)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('workflow', 'node_id')

    def __str__(self):
        return f"{self.workflow.name} - {self.node_id} ({self.type})"


class WorkflowEdge(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='edges')
    from_node_id = models.CharField(max_length=64)
    to_node_id = models.CharField(max_length=64)
    condition = models.CharField(
        max_length=50,
        blank=True,
        default='default',
        help_text="e.g. 'opened', 'clicked', 'default'"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('workflow', 'from_node_id', 'to_node_id', 'condition')

    def __str__(self):
        return f"{self.workflow.name}: {self.from_node_id} -> {self.to_node_id}"


class WorkflowEnrollment(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    ]

    contact = models.ForeignKey('contacts.Contact', on_delete=models.CASCADE, related_name='enrollments')
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='enrollments')
    current_node_id = models.CharField(max_length=64, blank=True, null=True)
    next_execution_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('contact', 'workflow')

    def __str__(self):
        return f"{self.contact.email} in {self.workflow.name}"
