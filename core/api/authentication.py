import hashlib
import hmac

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.api_keys.models import WorkspaceAPIKey
from core.tenant import set_current_tenant


class APIKeyAuthentication(BaseAuthentication):
    """Authenticate using an API key passed in the Authorization header.

    Format: Authorization: ApiKey <key_value>
    The key is looked up by its prefix (first 8 chars), then verified
    against the stored hash. Sets request.tenant to the key's workspace.
    """
    keyword = 'ApiKey'

    def authenticate(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', b'')
        if isinstance(auth, str):
            auth = auth.encode('utf-8')

        if not auth:
            return None

        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower().encode():
            return None

        raw_key = parts[1].decode('utf-8').strip()
        prefix = raw_key[:8]

        keys = WorkspaceAPIKey.objects.filter(prefix=prefix, is_active=True).select_related('workspace')
        for api_key in keys:
            if api_key.is_expired:
                continue
            expected_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
            if hmac.compare_digest(expected_hash, api_key.key_hash):
                api_key.record_usage()
                request.tenant = api_key.workspace
                set_current_tenant(api_key.workspace)
                return (api_key.workspace.created_by, api_key)

        return None

    def authenticate_header(self, request):
        return 'ApiKey'
