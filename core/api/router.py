from rest_framework.routers import DefaultRouter

from .views import (
    CampaignViewSet, EmailTemplateViewSet, SenderViewSet,
    EmailInboxViewSet, ContactListViewSet, ContactViewSet,
    ContactTagViewSet, ContactCustomFieldViewSet, ContactSegmentViewSet,
    SocialPostViewSet, ContentItemViewSet, MediaFolderViewSet,
    MediaAssetViewSet, WorkflowViewSet, SelfUserViewSet,
    WorkspaceMembershipViewSet, WorkspaceQuotaViewSet,
    )

router = DefaultRouter(trailing_slash=False)

router.register(r'me', SelfUserViewSet, basename='me')
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'email-templates', EmailTemplateViewSet, basename='email-template')
router.register(r'senders', SenderViewSet, basename='sender')
router.register(r'inboxes', EmailInboxViewSet, basename='inbox')
router.register(r'contact-lists', ContactListViewSet, basename='contact-list')
router.register(r'contacts', ContactViewSet, basename='contact')
router.register(r'contact-tags', ContactTagViewSet, basename='contact-tag')
router.register(r'contact-fields', ContactCustomFieldViewSet, basename='contact-field')
router.register(r'contact-segments', ContactSegmentViewSet, basename='contact-segment')
router.register(r'social-posts', SocialPostViewSet, basename='social-post')
router.register(r'content-items', ContentItemViewSet, basename='content-item')
router.register(r'media-folders', MediaFolderViewSet, basename='media-folder')
router.register(r'media-assets', MediaAssetViewSet, basename='media-asset')
router.register(r'workflows', WorkflowViewSet, basename='workflow')
router.register(r'members', WorkspaceMembershipViewSet, basename='member')
router.register(r'quota', WorkspaceQuotaViewSet, basename='quota')
