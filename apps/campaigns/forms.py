from django import forms
from django.core.validators import validate_email, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Campaign, CampaignVariant
from apps.senders.models import Sender
from apps.contacts.models import ContactList
from apps.workspaces.query_helpers import filter_by_context
from .services.content import text_to_html

class CampaignForm(forms.ModelForm):
    sender = forms.ModelChoiceField(
        queryset=Sender.objects.none(),
        required=False,
    )
    contact_list = forms.ModelChoiceField(
        queryset=ContactList.objects.none(),
        required=False,
        empty_label="— Select a contact list (optional) —",
    )

    # A/B Testing Fields
    is_ab_test = forms.BooleanField(
        required=False,
        label='Enable A/B Testing',
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-primary rounded border-gray-300 focus:ring-primary'}),
    )
    ab_test_duration_hours = forms.IntegerField(
        required=False,
        initial=2,
        min_value=1,
        max_value=168,
        label='Test Duration (hours)',
        widget=forms.NumberInput(attrs={'class': 'auth-input', 'placeholder': '2', 'min': '1', 'max': '168'}),
    )
    ab_percentage = forms.IntegerField(
        required=False,
        initial=20,
        min_value=5,
        max_value=50,
        label='Test Size (% of total)',
        help_text='Each variant receives this percentage. Remaining go to the winner.',
        widget=forms.NumberInput(attrs={'class': 'auth-input', 'placeholder': '20', 'min': '5', 'max': '50'}),
    )
    # Variant A fields
    variant_a_subject = forms.CharField(
        required=False,
        max_length=998,
        label='Variant A Subject',
        widget=forms.TextInput(attrs={'class': 'auth-input', 'placeholder': 'Variant A subject line'}),
    )
    variant_a_body = forms.CharField(
        required=False,
        label='Variant A Body',
        widget=forms.Textarea(attrs={'class': 'auth-input min-h-32', 'rows': 5, 'placeholder': 'Variant A email body...'}),
    )
    # Variant B fields
    variant_b_subject = forms.CharField(
        required=False,
        max_length=998,
        label='Variant B Subject',
        widget=forms.TextInput(attrs={'class': 'auth-input', 'placeholder': 'Variant B subject line'}),
    )
    variant_b_body = forms.CharField(
        required=False,
        label='Variant B Body',
        widget=forms.Textarea(attrs={'class': 'auth-input min-h-32', 'rows': 5, 'placeholder': 'Variant B email body...'}),
    )

    class Meta:
        model = Campaign
        fields = [
            'name', 'subject', 'from_name', 'reply_to', 'recipient_emails',
            'body_text', 'body_html', 'sender', 'scheduled_at',
            'is_ab_test', 'ab_test_duration_hours',
        ]
        widgets = {
            'recipient_emails': forms.Textarea(attrs={'rows': 4}),
            'body_text': forms.Textarea(attrs={'rows': 7}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        user = kwargs.pop('user', request.user if request else None)
        super().__init__(*args, **kwargs)
        self.fields['subject'].required = False
        self.fields['body_text'].required = False
        if user:
            sender_field = self.fields['sender']
            if isinstance(sender_field, forms.ModelChoiceField):
                if request:
                    sender_field.queryset = filter_by_context(request, Sender.objects.filter(is_active=True))
                else:
                    sender_field.queryset = Sender.objects.filter(user=user, is_active=True)
            contact_list_field = self.fields['contact_list']
            if isinstance(contact_list_field, forms.ModelChoiceField):
                if request:
                    contact_list_field.queryset = filter_by_context(request, ContactList.objects.all())
                else:
                    contact_list_field.queryset = ContactList.objects.filter(user=user)

        # If editing an existing A/B campaign, pre-fill variant fields
        if self.instance and self.instance.pk and self.instance.is_ab_test:
            variants = list(self.instance.variants.all().order_by('label'))
            if len(variants) >= 2:
                self.initial['variant_a_subject'] = variants[0].subject
                self.initial['variant_a_body'] = variants[0].body_text
                self.initial['variant_b_subject'] = variants[1].subject
                self.initial['variant_b_body'] = variants[1].body_text
                self.initial['ab_percentage'] = variants[0].percentage

    def clean_recipient_emails(self):
        value = (self.cleaned_data.get('recipient_emails') or '').strip()
        if not value:
            return ''
        cleaned = []
        for item in value.replace(';', ',').replace('\n', ',').split(','):
            email = item.strip().lower()
            if not email:
                continue
            try:
                validate_email(email)
            except ValidationError:
                raise forms.ValidationError(f'Invalid recipient email: {email}')
            if email not in cleaned:
                cleaned.append(email)
        return ', '.join(cleaned)

    def clean(self):
        cleaned_data = super().clean()
        is_ab = cleaned_data.get('is_ab_test')

        action = self.data.get('action', 'save_draft') if self.data else 'save_draft'
        is_draft_only = action in ('save_draft', 'send_test')

        if is_ab and not is_draft_only:
            var_a_subject = (cleaned_data.get('variant_a_subject') or '').strip()
            var_a_body = (cleaned_data.get('variant_a_body') or '').strip()
            var_b_subject = (cleaned_data.get('variant_b_subject') or '').strip()
            var_b_body = (cleaned_data.get('variant_b_body') or '').strip()

            if not var_a_subject or not var_a_body:
                self.add_error('variant_a_subject', 'Variant A subject and body are required for A/B testing.')
            if not var_b_subject or not var_b_body:
                self.add_error('variant_b_subject', 'Variant B subject and body are required for A/B testing.')
        elif not is_draft_only:
            subject = (cleaned_data.get('subject') or '').strip()
            if not subject:
                self.add_error('subject', 'Subject line is required before sending.')
            body_text = (cleaned_data.get('body_text') or '').strip()
            body_html = (cleaned_data.get('body_html') or '').strip()
            if body_text and not body_html:
                cleaned_data['body_html'] = '<p>' + body_text.replace('\n', '<br>') + '</p>'
            elif body_html and not body_text:
                import re
                cleaned_data['body_text'] = re.sub(r'<[^>]+>', '', body_html)
            if not cleaned_data.get('body_text') and not cleaned_data.get('body_html'):
                raise forms.ValidationError('Message content is required.')

        scheduled_at = cleaned_data.get('scheduled_at')
        if scheduled_at:
            now = timezone.now()
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
                cleaned_data['scheduled_at'] = scheduled_at
            if scheduled_at <= now:
                self.add_error('scheduled_at', 'Schedule time must be in the future.')
        return cleaned_data

    def save(self, commit=True):
        campaign = super().save(commit=False)
        if commit:
            campaign.save()
            self._save_variants(campaign)
            self._sync_ab_fields(campaign)
        return campaign

    def _save_variants(self, campaign):
        if not self.cleaned_data.get('is_ab_test'):
            campaign.variants.all().delete()
            return

        ab_percentage = self.cleaned_data.get('ab_percentage', 20)
        variants_data = [
            {
                'label': 'A',
                'subject': self.cleaned_data.get('variant_a_subject', ''),
                'body_text': self.cleaned_data.get('variant_a_body', ''),
                'body_html': text_to_html(self.cleaned_data.get('variant_a_body', '')),
                'percentage': ab_percentage,
            },
            {
                'label': 'B',
                'subject': self.cleaned_data.get('variant_b_subject', ''),
                'body_text': self.cleaned_data.get('variant_b_body', ''),
                'body_html': text_to_html(self.cleaned_data.get('variant_b_body', '')),
                'percentage': ab_percentage,
            },
        ]

        existing = {v.label: v for v in campaign.variants.all()}
        for vdata in variants_data:
            if vdata['label'] in existing:
                variant = existing[vdata['label']]
                variant.subject = vdata['subject']
                variant.body_text = vdata['body_text']
                variant.percentage = vdata['percentage']
                variant.save()
            else:
                CampaignVariant.objects.create(campaign=campaign, **vdata)

        # Remove extra variants (shouldn't happen but guard against stale data)
        campaign.variants.exclude(label__in=['A', 'B']).delete()

    def _sync_ab_fields(self, campaign):
        is_ab = self.cleaned_data.get('is_ab_test', False)
        campaign.is_ab_test = is_ab
        if is_ab:
            campaign.ab_test_duration_hours = self.cleaned_data.get('ab_test_duration_hours', 2)
            campaign.ab_test_status = 'pending'
            # Copy first variant's content as campaign fallback
            first_var = campaign.variants.filter(label='A').first()
            if first_var:
                campaign.subject = first_var.subject
                campaign.body_text = first_var.body_text
        else:
            campaign.ab_test_status = 'pending'
            campaign.is_ab_test = False
        campaign.save(update_fields=['is_ab_test', 'ab_test_status', 'ab_test_duration_hours', 'subject', 'body_text', 'updated_at'])