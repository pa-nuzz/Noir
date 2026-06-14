from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.tenant import get_current_tenant
from core.api.permissions import TenantPermission, TenantModelPermission, IsWorkspaceAdminOrReadOnly
from core.api.serializers import (
    UserSerializer, SenderSerializer, CampaignSerializer, EmailTemplateSerializer,
    EmailInboxSerializer, ContactListSerializer, ContactSerializer,
    ContactTagSerializer, ContactCustomFieldSerializer, ContactSegmentSerializer,
    SocialPostSerializer, ContentItemSerializer, MediaFolderSerializer,
    MediaAssetSerializer, WorkflowSerializer, WorkspaceMembershipSerializer,
    WorkspaceQuotaSerializer,
)
from apps.accounts.models import User
from apps.campaigns.models import Campaign, EmailTemplate
from apps.senders.models import Sender
from apps.inbox.models import EmailInbox
from apps.contacts.models import ContactList, Contact, ContactTag, ContactCustomField, ContactSegment
from apps.social_accounts.models import SocialPost
from apps.content_studio.models import ContentItem
from apps.media_assets.models import MediaFolder, MediaAsset
from apps.automations.models import Workflow
from apps.workspaces.models import WorkspaceMembership, WorkspaceQuota


class TenantAwareMixin:
    """Mixin that filters queryset by the current tenant."""

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is not None:
            return qs.filter(workspace=tenant)
        return qs.none()

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        if tenant is None:
            raise PermissionError('No active tenant')
        serializer.save(workspace=tenant, user=self.request.user)

    def perform_update(self, serializer):
        serializer.save()


class SelfUserViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [TenantPermission]

    def get_object(self):
        return self.request.user


class CampaignViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [TenantModelPermission]


class EmailTemplateViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = EmailTemplateSerializer
    permission_classes = [TenantModelPermission]


class SenderViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = SenderSerializer
    permission_classes = [TenantModelPermission]


class EmailInboxViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = EmailInboxSerializer
    permission_classes = [TenantModelPermission]

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        inbox = self.get_object()
        from apps.inbox.tasks import sync_inbox_task
        sync_inbox_task.delay(inbox.id)
        return Response({'status': 'sync_queued'})


class ContactListViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = ContactListSerializer
    permission_classes = [TenantModelPermission]


class ContactViewSet(viewsets.ModelViewSet):
    serializer_class = ContactSerializer
    permission_classes = [TenantModelPermission]

    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant is None:
            return Contact.objects.none()
        return Contact.objects.filter(contact_list__workspace=tenant)

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        if tenant is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Active workspace required to create contacts.')
        contact_list = serializer.validated_data.get('contact_list')
        if contact_list and contact_list.workspace_id != tenant.id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'contact_list': 'Contact list does not belong to this workspace.'})
        serializer.save()


class ContactTagViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = ContactTagSerializer
    permission_classes = [TenantModelPermission]


class ContactCustomFieldViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = ContactCustomFieldSerializer
    permission_classes = [TenantModelPermission]


class ContactSegmentViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = ContactSegmentSerializer
    permission_classes = [TenantModelPermission]


class SocialPostViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = SocialPostSerializer
    permission_classes = [TenantModelPermission]


class ContentItemViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = ContentItemSerializer
    permission_classes = [TenantModelPermission]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        item = self.get_object()
        item.status = 'approved'
        item.save(update_fields=['status'])
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        item = self.get_object()
        item.status = 'published'
        item.save(update_fields=['status'])
        return Response({'status': 'published'})


class MediaFolderViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = MediaFolderSerializer
    permission_classes = [TenantModelPermission]


class MediaAssetViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = MediaAssetSerializer
    permission_classes = [TenantModelPermission]


class WorkflowViewSet(TenantAwareMixin, viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [TenantModelPermission]


class WorkspaceMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [TenantPermission]

    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant is None:
            return WorkspaceMembership.objects.none()
        return WorkspaceMembership.objects.filter(workspace=tenant).select_related('user')


class WorkspaceQuotaViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = WorkspaceQuotaSerializer
    permission_classes = [TenantPermission]

    def get_object(self):
        tenant = get_current_tenant()
        if tenant is None:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        quota, _ = WorkspaceQuota.objects.get_or_create(workspace=tenant)
        quota.reset_monthly_if_needed()
        return quota
