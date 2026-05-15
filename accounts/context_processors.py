def auth_required(request):
    return {
        'requires_auth': request.user.is_authenticated
    }