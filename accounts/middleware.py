from django.utils.cache import add_never_cache_headers

class DisableCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Apply to ALL pages, not just authenticated ones
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'

        # ✅ This specifically opts out of Chrome/Edge bfcache
        response['Clear-Site-Data'] = '"cache"'
        return 