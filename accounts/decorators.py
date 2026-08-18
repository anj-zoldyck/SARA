from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from functools import wraps

def session_protected(view_func=None, *, timeout=900, extend_session=True):
    """
    Decorator that enforces session authentication and sets session expiry.
    
    Supports both bare usage (@session_protected) and parameterized usage (@session_protected(timeout=1800)).
    - Default timeout: 900 seconds (15 minutes)
    - Kiosk views (scan_rfid family): 1800 seconds (30 minutes)
    - extend_session=False: Skip session expiry extension (for pure polling endpoints)
    
    The decorator-factory pattern allows both:
        @session_protected  # uses default 900s, extends session
        @session_protected(timeout=1800)  # custom timeout, extends session
        @session_protected(extend_session=False)  # no session extension
    
    Background polling detection:
        If request contains X-Background-Poll: true header, session expiry is not extended
        (used by scan_rfid refreshTable() polling to prevent indefinite session extension)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            # Check if this is a background polling request
            is_background_poll = request.headers.get('X-Background-Poll') == 'true'
            # Set session expiry to rolling timeout from last activity, unless:
            # - extend_session=False is explicitly set, OR
            # - X-Background-Poll header is present
            if extend_session and not is_background_poll:
                request.session.set_expiry(timeout)
            return func(request, *args, **kwargs)
        return wrapper
    
    if view_func is None:
        # Called with arguments: @session_protected(timeout=1800)
        return decorator
    else:
        # Called without arguments: @session_protected
        return decorator(view_func)

def mswdo_or_staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
            return HttpResponseForbidden("Access Denied")
        return view_func(request, *args, **kwargs)
    return wrapper