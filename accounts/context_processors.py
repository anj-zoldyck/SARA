def auth_required(request):
    return {
        'requires_auth': request.user.is_authenticated
    }


def offline_sync_metadata(request):
    """
    Makes the last full sync metadata available in templates for the persistent banner.
    """
    from distribution.models import OfflineSyncMetadata
    
    if request.user.is_authenticated and request.user.role == 'MSWDO_STAFF':
        latest_sync = OfflineSyncMetadata.get_latest_sync()
        return {
            'latest_sync': latest_sync,
        }
    return {}