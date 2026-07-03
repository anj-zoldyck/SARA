from django.shortcuts import redirect
from django.urls import reverse

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'must_change_password', False):
            # Prevent infinite redirect loops by allowing access to force_password_change and logout
            allowed_paths = [
                reverse('force_password_change'),
                reverse('logout'),
            ]
            # Optionally, you might want to allow access to static files and media
            if request.path not in allowed_paths and not request.path.startswith('/static/') and not request.path.startswith('/media/'):
                return redirect('force_password_change')

        response = self.get_response(request)
        return response