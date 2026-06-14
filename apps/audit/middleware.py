import threading


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        threading._audit_user = request.user if request.user.is_authenticated else None
        threading._audit_ip = request.META.get('REMOTE_ADDR')
        response = self.get_response(request)
        threading._audit_user = None
        threading._audit_ip = None
        return response
