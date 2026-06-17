import json

from django.db import models
from django.db.models import Q
from django.conf import settings

from core.models import AuditMixin
from core.tenant import TenantManager


class ContactList(AuditMixin):
    objects = TenantManager()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_lists')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='contact_lists')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_email_list(self):
        return list(self.contacts.filter(is_active=True, unsubscribed=False).values_list('email', flat=True))


class ContactTag(AuditMixin):
    objects = TenantManager()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_tags')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='contact_tags')
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'name'], condition=Q(workspace__isnull=False), name='unique_tag_per_workspace'),
            models.UniqueConstraint(fields=['user', 'name'], condition=Q(workspace__isnull=True), name='unique_tag_per_user'),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name


class ContactCustomField(AuditMixin):
    objects = TenantManager()
    FIELD_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Yes/No'),
        ('dropdown', 'Dropdown'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='custom_fields')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='contact_custom_fields')
    name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES, default='text')
    options = models.JSONField(default=list, blank=True, help_text='Options for dropdown type')
    is_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'name'], condition=Q(workspace__isnull=False), name='unique_custom_field_per_workspace'),
            models.UniqueConstraint(fields=['user', 'name'], condition=Q(workspace__isnull=True), name='unique_custom_field_per_user'),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name


class ContactSegment(AuditMixin):
    objects = TenantManager()
    MATCH_CHOICES = [
        ('all', 'Match ALL conditions'),
        ('any', 'Match ANY condition'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_segments')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='contact_segments')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    match_type = models.CharField(max_length=5, choices=MATCH_CHOICES, default='all')
    rules = models.JSONField(default=list, blank=True, help_text='List of rule objects: {"field": "...", "operator": "...", "value": "..."}')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_matched_contacts(self):
        from django.db.models import Q
        if self.workspace_id:
            qs = Contact.objects.filter(contact_list__workspace=self.workspace)
        else:
            qs = Contact.objects.filter(contact_list__user=self.user)
        if not self.rules:
            return qs.none()

        queries = []
        for rule in self.rules:
            field = rule.get('field', '')
            operator = rule.get('operator', '')
            value = rule.get('value', '')

            if field == 'email':
                if operator == 'contains':
                    queries.append(Q(email__icontains=value))
                elif operator == 'equals':
                    queries.append(Q(email__iexact=value))
                elif operator == 'starts_with':
                    queries.append(Q(email__istartswith=value))
                elif operator == 'ends_with':
                    queries.append(Q(email__iendswith=value))
            elif field == 'first_name':
                if operator == 'contains':
                    queries.append(Q(first_name__icontains=value))
                elif operator == 'equals':
                    queries.append(Q(first_name__iexact=value))
            elif field == 'last_name':
                if operator == 'contains':
                    queries.append(Q(last_name__icontains=value))
                elif operator == 'equals':
                    queries.append(Q(last_name__iexact=value))
            elif field == 'is_active':
                queries.append(Q(is_active=(value.lower() == 'true')))
            elif field == 'unsubscribed':
                queries.append(Q(unsubscribed=(value.lower() == 'true')))
            elif field == 'bounce_count':
                try:
                    val = int(value)
                    if operator == 'gt':
                        queries.append(Q(bounce_count__gt=val))
                    elif operator == 'gte':
                        queries.append(Q(bounce_count__gte=val))
                    elif operator == 'lt':
                        queries.append(Q(bounce_count__lt=val))
                    elif operator == 'lte':
                        queries.append(Q(bounce_count__lte=val))
                    elif operator == 'equals':
                        queries.append(Q(bounce_count=val))
                except (ValueError, TypeError):
                    pass
            elif field == 'created_at':
                if operator == 'before':
                    queries.append(Q(created_at__date__lt=value))
                elif operator == 'after':
                    queries.append(Q(created_at__date__gt=value))
            elif field == 'tag':
                if operator == 'has':
                    queries.append(Q(tags__name__iexact=value))
                elif operator == 'not_has':
                    queries.append(~Q(tags__name__iexact=value))
            elif field == 'contact_list':
                if operator == 'is':
                    queries.append(Q(contact_list__name__iexact=value))
                elif operator == 'is_not':
                    queries.append(~Q(contact_list__name__iexact=value))

        if not queries:
            return qs.none()

        if self.match_type == 'all':
            combined = queries[0]
            for q in queries[1:]:
                combined &= q
        else:
            combined = queries[0]
            for q in queries[1:]:
                combined |= q

        return qs.filter(combined).distinct()


class Contact(AuditMixin):
    objects = TenantManager(related_filter='contact_list__workspace')
    contact_list = models.ForeignKey(ContactList, on_delete=models.CASCADE, related_name='contacts')
    email = models.EmailField()
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    tags = models.ManyToManyField(ContactTag, blank=True, related_name='contacts')

    # Unsubscribe management
    unsubscribed = models.BooleanField(default=False)
    unsubscribed_at = models.DateTimeField(blank=True, null=True)
    unsubscribed_from_list = models.BooleanField(default=False, help_text='List-level unsubscribe')

    # Bounce tracking — auto-suppress after 3 bounces
    bounce_count = models.IntegerField(default=0)
    last_bounce_at = models.DateTimeField(blank=True, null=True)
    is_suppressed = models.BooleanField(default=False, help_text='Auto-suppressed due to bounces')

    # GDPR compliance
    gdpr_consent = models.BooleanField(default=False)
    gdpr_consent_at = models.DateTimeField(blank=True, null=True)
    gdpr_data_exported_at = models.DateTimeField(blank=True, null=True)
    gdpr_notes = models.TextField(blank=True, help_text='GDPR consent source or notes')

    # General
    notes = models.TextField(blank=True)
    last_activity_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('contact_list', 'email')
        ordering = ['email']
        indexes = [
            models.Index(fields=['contact_list', 'email']),
            models.Index(fields=['is_active', 'unsubscribed']),
        ]

    def __str__(self):
        return self.email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_unsubscribed = self.unsubscribed

    def record_bounce(self):
        self.bounce_count += 1
        self.last_bounce_at = __import__('django').utils.timezone.now()
        if self.bounce_count >= 3:
            self.is_suppressed = True
        self.save(update_fields=['bounce_count', 'last_bounce_at', 'is_suppressed', 'updated_at'])

    def unsubscribe(self, list_level=False):
        self.unsubscribed = True
        self.unsubscribed_at = __import__('django').utils.timezone.now()
        if list_level:
            self.unsubscribed_from_list = True
        self.save(update_fields=['unsubscribed', 'unsubscribed_at', 'unsubscribed_from_list', 'updated_at'])

    @staticmethod
    def parse_tags(raw_tags: str) -> list[str]:
        if not raw_tags:
            return []
        cleaned: list[str] = []
        for token in raw_tags.replace(';', ',').split(','):
            tag = token.strip()
            if not tag:
                continue
            normalized = ' '.join(tag.split())
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned


class ContactCustomFieldValue(AuditMixin):
    objects = TenantManager(related_filter='contact__contact_list__workspace')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='custom_field_values')
    field = models.ForeignKey(ContactCustomField, on_delete=models.CASCADE)
    value = models.TextField(blank=True)

    class Meta:
        unique_together = ('contact', 'field')
        verbose_name_plural = 'Custom field values'

    def __str__(self):
        return f"{self.field.name}: {self.value}"