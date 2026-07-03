
from urllib import request
from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Count, Q

from accounts.decorators import session_protected
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AidClaim

from accounts.forms import UserEditForm, CreateUserForm, ProfileSettingsForm, ProfilePasswordChangeForm
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm
from programs.forms import ProgramForm, AidCategoryForm, AssistanceForm

# Removed unused invitation email imports
# from distribution.forms import AidScheduleForm  # if any

from django.utils.safestring import mark_safe
from distribution.services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from django.urls import reverse
from django.core.cache import cache
import json

User = get_user_model()


def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'MSWDO':
            return redirect('mswdo_dashboard')
        elif request.user.role == 'MSWDO_STAFF':
            return redirect('staff_dashboard')
        else:
            return redirect('barangay_dashboard')

    if request.method == "POST":
        # Rate limiting — max 5 attempts per IP per minute
        ip = request.META.get('REMOTE_ADDR')
        cache_key = f'login_attempts_{ip}'
        attempts = cache.get(cache_key, 0)

        if attempts >= 5:
            messages.error(request, "Too many login attempts. Please wait a minute and try again.")
            response = render(request, 'accounts/login.html')
            response['Cache-Control'] = 'no-store'
            return response

        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, "Account is deactivated.")
            else:
                cache.delete(cache_key)  # Reset attempts on successful login
                login(request, user)
                if user.must_change_password:
                    response = redirect('force_password_change')
                else:
                    if user.role == 'MSWDO':
                        response = redirect('mswdo_dashboard')
                    elif user.role == 'MSWDO_STAFF':
                        response = redirect('staff_dashboard')
                    else:
                        response = redirect('barangay_dashboard')
                response.set_cookie('sara_auth', '1', samesite='Lax')
                return response
        else:
            # Increment failed attempts, expire after 60 seconds
            cache.set(cache_key, attempts + 1, timeout=60)
            messages.error(request, "Invalid username or password.")

    response = render(request, 'accounts/login.html')
    response['Cache-Control'] = 'no-store'
    return response


def logout_view(request):
    logout(request)
    request.session.flush()

    response = HttpResponseRedirect(reverse('landing'))
    #Aggressively kill the cache on the redirect itself
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    #Clears the browser's back-forward cache for this origin
    response['Clear-Site-Data'] = '"cache"'

    # Explicitly overwrite sara_auth with expired cookie
    response.set_cookie(
        'sara_auth',
        '',
        max_age=0,
        expires='Thu, 01 Jan 1970 00:00:00 GMT',
        samesite='Lax'
    )
    return response


def landing_page(request):
    return render(request, 'accounts/landing.html', {
        'hide_navbar': True
    })


def check_session(request):
    if request.user.is_authenticated:
        return JsonResponse({'authenticated': True})
    return JsonResponse({'authenticated': False}, status=401)


import secrets
import string

def generate_temp_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@login_required(login_url='login')
@session_protected
def create_user(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            temp_password = generate_temp_password()
            user.set_password(temp_password)
            user.is_active = True
            user.must_change_password = True
            user.save()
            return render(request, 'accounts/create_user_success.html', {
                'created_user': user,
                'temp_password': temp_password,
            })
    else:
        form = CreateUserForm()

    return render(request, 'accounts/create_user.html', {'form': form})


@login_required(login_url='login')
def force_password_change(request):
    if not request.user.must_change_password:
        if request.user.role == 'MSWDO':
            return redirect('mswdo_dashboard')
        elif request.user.role == 'MSWDO_STAFF':
            return redirect('staff_dashboard')
        else:
            return redirect('barangay_dashboard')

    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password and new_password == confirm_password and len(new_password) >= 8:
            request.user.set_password(new_password)
            request.user.must_change_password = False
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password updated successfully. Welcome to SARA!")
            if request.user.role == 'MSWDO':
                return redirect('mswdo_dashboard')
            elif request.user.role == 'MSWDO_STAFF':
                return redirect('staff_dashboard')
            else:
                return redirect('barangay_dashboard')
        else:
            messages.error(request, "Passwords do not match or are less than 8 characters.")

    return render(request, 'accounts/force_password_change.html')


@login_required(login_url='login')
@session_protected
def edit_user(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    user_obj = get_object_or_404(User, id=user_id, role__in=['BARANGAY', 'MSWDO_STAFF'])

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Email for {user_obj.username} updated successfully.")
            return redirect('user_accounts')
    else:
        form = UserEditForm(instance=user_obj)

    return render(request, 'accounts/edit_user.html', {
        'form': form,
        'user_obj': user_obj,
    })


@login_required(login_url='login')
@session_protected
def deactivate_user(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    user_obj = get_object_or_404(User, id=user_id, role__in=['BARANGAY', 'MSWDO_STAFF'])
    user_obj.is_active = False
    user_obj.save()
    
    return redirect('user_accounts')


@login_required(login_url='login')
@session_protected
def activate_user_account(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    user_obj = get_object_or_404(User, id=user_id, role__in=['BARANGAY', 'MSWDO_STAFF'])
    user_obj.is_active = True
    user_obj.save()

    return redirect('user_accounts')


@login_required(login_url='login')
@session_protected
def user_accounts(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    
    # Base queryset excluding MSWDO Admin
    users = User.objects.filter(role__in=['BARANGAY', 'MSWDO_STAFF']).select_related('barangay')
    
    # Filtering logic
    role_filter = request.GET.get('role', '')
    barangay_filter = request.GET.get('barangay', '')

    if role_filter in ['MSWDO_STAFF', 'BARANGAY']:
        users = users.filter(role=role_filter)
        if role_filter == 'BARANGAY' and barangay_filter:
            users = users.filter(barangay_id=barangay_filter)

    users = users.order_by('-date_joined')
    active_count = users.filter(is_active=True).count()
    
    # We need all barangays for the filter dropdown
    barangays = Barangay.objects.all().order_by('name')

    return render(request, 'accounts/user_accounts.html', {
        'users': users,
        'active_count': active_count,
        'barangays': barangays,
        'selected_role': role_filter,
        'selected_barangay': barangay_filter,
    })


def verify_otp(request):
    if request.method == 'POST':
        otp_token = request.POST.get('otp_token')
        user = request.session.get('pre_2fa_user_id')

        device = EmailDevice.objects.filter(user_id=user, confirmed=True).first()
        if device and device.verify_token(otp_token):
            login(request, get_user_model().objects.get(pk=user),
                  backend='accounts.backends.EmailBackend')
            return redirect('dashboard')
        else:
            return render(request, 'accounts/verify_otp.html', {'error': 'Invalid OTP'})

    return render(request, 'accounts/verify_otp.html')


def send_otp(request, user):
    device, _ = EmailDevice.objects.get_or_create(user=user, defaults={'name': 'email'})
    device.generate_challenge()  # sends OTP via Brevo SMTP


#Settings view for logged-in users to edit their own profile
@login_required(login_url='login')
@session_protected
def settings_view(request):
    """
    One shared settings page for all 3 roles (MSWDO Admin, MSWDO Staff,
    Barangay Admin). Role-specific field locking (e.g. username editable
    only for MSWDO Admin) is handled inside ProfileSettingsForm, not here —
    this view stays role-agnostic on purpose, the same way base.html
    handles sidebar rendering: one template/view, conditional fields.
 
    Two independent forms live on this one page, distinguished by a
    hidden 'form_type' field in each <form> so a single view function
    can tell which one was submitted:
      - 'profile'  -> ProfileSettingsForm  (name, contact info, photo, etc.)
      - 'password' -> ProfilePasswordChangeForm (modal, requires current pw)
    """
    profile_form = ProfileSettingsForm(instance=request.user)
    password_form = ProfilePasswordChangeForm(user=request.user)
 
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
 
        if form_type == 'profile':
            profile_form = ProfileSettingsForm(
                request.POST, request.FILES, instance=request.user
            )
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Please correct the errors below.")
 
        elif form_type == 'password':
            password_form = ProfilePasswordChangeForm(
                user=request.user, data=request.POST
            )
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data['new_password'])
                request.user.save()
                # CRITICAL: without this, Django invalidates the current
                # session hash after set_password() and immediately logs
                # the user out mid-action, which would look like a bug.
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password changed successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Please correct the errors below and try again.")
 
    return render(request, 'accounts/settings.html', {
        'profile_form': profile_form,
        'password_form': password_form,
    })

#-------------------Update Profile Photo View-----------------
@login_required(login_url='login')
@session_protected
def update_profile_photo(request):
    """
    Dedicated endpoint for the photo-upload modal on the settings page.

    Why this exists instead of reusing ProfileSettingsForm:
    ProfileSettingsForm requires first_name/last_name/email (they're
    required model fields), so submitting ONLY a photo through that
    form always fails validation — and a failed validation re-render
    shows an EMPTY form (since Django re-displays exactly what was
    POSTed, not what's saved), which looks like the user's other data
    got wiped even though it's untouched in the database.

    This view sidesteps that entirely: it touches ONLY profile_image.
    """
    if request.method == 'POST' and request.FILES.get('profile_image'):
        request.user.profile_image = request.FILES['profile_image']
        request.user.save(update_fields=['profile_image'])
        messages.success(request, "Profile photo updated successfully.")
    else:
        messages.error(request, "Please choose an image to upload.")

    return redirect('settings')

# ============================================================
# ADD THIS TO accounts/views.py
# (Pair with update_profile_photo — handles the "Remove Photo" action)
# ============================================================

@login_required(login_url='login')
@session_protected
def remove_profile_photo(request):
    """
    Deletes the current user's profile photo, both the file on disk
    and the reference on the User model, reverting their avatar back
    to the initials fallback (e.g. "JD") used throughout base.html.
    """
    if request.method == 'POST':
        if request.user.profile_image:
            # .delete(save=False) removes the actual file from
            # MEDIA_ROOT; save=False because we call user.save()
            # ourselves right after, in one DB write.
            request.user.profile_image.delete(save=False)
            request.user.profile_image = None
            request.user.save(update_fields=['profile_image'])
            messages.success(request, "Profile photo removed.")
        else:
            messages.info(request, "You don't have a profile photo to remove.")

    return redirect('settings')