from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from functools import wraps

def session_protected(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper