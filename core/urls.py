from django.contrib import admin
import core.admin  # ensure admin site branding is applied
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView
from django.conf import settings
from django.conf.urls.static import static
from core.views import landing_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + [
    path('admin/', admin.site.urls),
    path('', landing_view, name='home'),
    path('senders/', include('apps.senders.urls', namespace='senders')),
    path('contacts/', include('apps.contacts.urls', namespace='contacts')),
    path('campaign/', include('apps.campaigns.urls', namespace='campaigns')),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('dashboard/', include('apps.dashboard.urls', namespace='dashboard')),
    path('intelligence/', include('apps.intelligence.urls', namespace='intelligence')),
    path('automations/', include('apps.automations.urls', namespace='automations')),
    path('inbox/', include('apps.inbox.urls', namespace='inbox')),
    path('social/', include('apps.social.urls', namespace='social')),
    path('social/', RedirectView.as_view(url='/social-accounts/', permanent=True), name='social_legacy'),
    path('content/', RedirectView.as_view(url='/content-studio/', permanent=True), name='content_legacy'),
    path('media/', RedirectView.as_view(url='/media-assets/', permanent=True), name='media_legacy'),
    path('workspaces/', include('apps.workspaces.urls', namespace='workspaces')),
    path('social-accounts/', include('apps.social_accounts.urls', namespace='social_accounts')),
    path('content-studio/', include('apps.content_studio.urls', namespace='content_studio')),
    path('media-assets/', include('apps.media_assets.urls', namespace='media_assets')),
    path('creative/', include('apps.creative.urls', namespace='creative')),
    path('trending/', include('apps.trending.urls', namespace='trending')),
    path('billing/', include('apps.billing.urls', namespace='billing')),
    path('webhooks/', include('apps.webhooks.urls', namespace='webhooks')),
    path('mfa/', include('apps.mfa.urls', namespace='mfa')),
    path('api/v1/', include('core.api.urls', namespace='api')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('terms/', TemplateView.as_view(template_name='terms.html'), name='terms'),
    path('cookies/', TemplateView.as_view(template_name='cookies.html'), name='cookies'),

    path('robots.txt', TemplateView.as_view(
        template_name='robots.txt',
        content_type='text/plain'
    ), name='robots_txt'),
]


