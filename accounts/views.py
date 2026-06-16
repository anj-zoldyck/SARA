from urllib import request
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Count, Q

from accounts.decorators import session_protected
from .models import AidSchedule,  User, Household, Zone, Family, FamilyMember, Barangay, AidClaim, Program, AidCategory, Assistance
from .forms import BarangayAdminEditForm, HouseholdForm, FamilyForm, FamilyMemberForm, BarangayAdminForm, ProgramForm, AidCategoryForm, AssistanceForm
from django.utils.safestring import mark_safe
from .services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from django.urls import reverse
from django.core.cache import cache
import json

def check_session(request):
    if request.user.is_authenticated:
        return JsonResponse({'authenticated': True})
    return JsonResponse({'authenticated': False}, status=401)

def landing_page(request):
    return render(request, 'accounts/landing.html', {
        'hide_navbar': True
    })

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


def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'MSWDO':
            return redirect('mswdo_dashboard')
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
                if user.role == 'MSWDO':
                    response = redirect('mswdo_dashboard')
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

User = get_user_model()

#----------------- Rate Limit Error Handler -----------------
#def ratelimit_error(request, exception=None):
    #return render(request, 'accounts/429.html', status=429)

#----------------- MSWDO Dashboard View -----------------
@login_required(login_url='login')
@session_protected
def mswdo_dashboard(request):
    # Only MSWDO can access
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    # Summary counts
    barangay_accounts = User.objects.filter(role='BARANGAY')
    barangayAcc_count = barangay_accounts.count()
    barangay_count = Barangay.objects.count()
    barangays = Barangay.objects.all()


    household_count = Household.objects.count()  # Total households
    family_count = Family.objects.count()        # Total families

    # RFID stats (assumes you track claimed/unclaimed in AidClaim model)
    rfid_claimed = AidClaim.objects.filter(claimed_at__isnull=False).count()
    rfid_unclaimed = AidClaim.objects.filter(claimed_at__isnull=True).count()

    # NEW: pass active assistance options for the schedule form
    assistances = Assistance.objects.select_related(
        'program', 'aid_category'
    ).filter(is_active=True).order_by('program__name', 'aid_category__name')

    now = timezone.localtime(timezone.now())

    # Auto-deactivate expired schedules every time dashboard loads
    AidSchedule.objects.filter(end_datetime__lt=now, is_active=True).update(is_active=False)
    # ACTIVE (ongoing)
    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        end_datetime__gte=now,
        is_active=True
    )

    # UPCOMING
    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_active=True
    )

    # EXPIRED
    expired_schedules = AidSchedule.objects.filter(
        end_datetime__lt=now
    )

    # Auto-deactivate all expired schedules
    expired = AidSchedule.objects.filter(end_datetime__lt=now)
    count = expired.update(is_active=False)
    print(f"Deactivated {count} expired schedules.")


    context = {
        'barangays': barangays,
        'barangay_accounts': barangay_accounts,  # For table
        'barangay_count': barangay_count,
        'household_count': household_count,
        'family_count': family_count,
        'rfid_claimed': rfid_claimed,
        'rfid_unclaimed': rfid_unclaimed,
       'assistances': assistances,
        'barangayAcc_count': barangayAcc_count,
        #'schedules': schedules,

        'active_schedules': active_schedules,
        'upcoming_schedules': upcoming_schedules,
        'expired_schedules': expired_schedules,
    }

    return render(request, 'accounts/mswdo_dashboard.html', context)



@login_required(login_url='login')
@session_protected
def create_barangay(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = BarangayAdminForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'BARANGAY'
            user.set_password(form.cleaned_data['password'])
            user.save()
            return redirect('mswdo_dashboard')
    else:
        form = BarangayAdminForm()
        print(form.errors)


    return render(request, 'accounts/create_barangay.html', {'form': form})

    # If GET request, show the form
    barangays = Barangay.objects.all()  # send all Barangay instances to the template
    return render(request, 'accounts/create_barangay.html', {'barangays': barangays})

@login_required(login_url='login')
@session_protected
def deactivate_barangay(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = get_object_or_404(User, id=user_id, role='BARANGAY')
    barangay.is_active = False
    barangay.save()
    
    return redirect('barangay_accounts')

# ── Activate Barangay ─────────────────────────────────────────
@login_required(login_url='login')
@session_protected
def activate_barangay(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = get_object_or_404(User, id=user_id, role='BARANGAY')
    barangay.is_active = True
    barangay.save()

    return redirect('barangay_accounts')  # or 'mswdo_dashboard' if you prefer


# ── Edit Barangay ──────────────────────────────────────────────
@login_required(login_url='login')
@session_protected
def edit_barangay(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = get_object_or_404(User, id=user_id, role='BARANGAY')

    if request.method == 'POST':
        form = BarangayAdminEditForm(request.POST, instance=barangay)
        if form.is_valid():
            user = form.save(commit=False)
            # Only update password if a new one was provided
            new_password = form.cleaned_data.get('password')
            if new_password:
                user.set_password(new_password)
            user.save()
            return redirect('barangay_accounts')
    else:
        form = BarangayAdminEditForm(instance=barangay)

    return render(request, 'accounts/edit_barangay.html', {
        'form': form,
        'barangay': barangay,
    })

@login_required(login_url='login')
@session_protected
def barangay_dashboard(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay_name = request.user.barangay
    zones = Zone.objects.filter(barangay=barangay_name)  # <-- Here

    now = timezone.now()
    schedules = AidSchedule.objects.filter(
        is_active=True,
        schedule_datetime__gte=now
    ).filter(
        Q(barangay=request.user.barangay) |
        Q(barangay__isnull=True)
    )

    return render(request, 'barangay/dashboard.html', {
        'barangay': barangay_name,
        'zones': zones,
        'schedules': schedules
    })


@login_required(login_url='login')
@session_protected
def barangay_accounts(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    
    barangays = User.objects.filter(role='BARANGAY')
    active_count = barangays.filter(is_active=True).count()
    return render(request, 'accounts/barangay_accounts.html', {
        'barangays': barangays,
        'active_count': active_count
    })


@login_required(login_url='login')
@session_protected
def zone_detail(request, zone_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    households = Household.objects.filter(zone=zone)

    return render(request, 'barangay/zone_detail.html', {
        'zone': zone,
        'households': households
    })

#household detail
@login_required(login_url='login')
@session_protected
def household_detail(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    household = get_object_or_404(
        Household,
        id=household_id,
        barangay=request.user.barangay
    )

    families = household.families.all()

    return render(request, 'barangay/household_detail.html', {
        'household': household,
        'families': families
    })


#add household
@login_required(login_url='login')
@session_protected
def add_household(request, zone_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(
        Zone,
        id=zone_id,
        barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = HouseholdForm(request.POST)
        if form.is_valid():
            household = form.save(commit=False)
            household.zone = zone
            household.barangay = request.user.barangay
            household.save()

            return redirect('zone_detail', zone_id=zone.id)
    else:
        form = HouseholdForm()

    return render(request, 'barangay/add_household.html', {
        'form': form,
        'zone': zone
    })

@login_required
@session_protected
def add_family(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    household = get_object_or_404(
        Household,
        id=household_id,
        barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = FamilyForm(request.POST)
        if form.is_valid():
            family = form.save(commit=False)
            family.household = household
            family.save()
            return redirect('household_detail', household_id=household.id)
    else:
        form = FamilyForm()

    return render(request, 'barangay/add_family.html', {
        'form': form,
        'household': household
    })

#family detail
@login_required
@session_protected
def family_detail(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(
        Family,
        id=family_id,
        household__barangay=request.user.barangay
    )

    members = family.members.all()

    return render(request, 'barangay/family_detail.html', {
        'family': family,
        'members': members
    })

#add family member
@login_required
@session_protected
def add_family_member(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(
        Family,
        id=family_id,
        household__barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = FamilyMemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.family = family
            member.save()
            return redirect('family_detail', family_id=family.id)
    else:
        form = FamilyMemberForm()

    return render(request, 'barangay/add_member.html', {
        'form': form,
        'family': family
    })

#edit family member
@login_required
@session_protected
def edit_family_member(request, member_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    member = get_object_or_404(
        FamilyMember,
        id=member_id,
        family__household__barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = FamilyMemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            return redirect('family_detail', family_id=member.family.id)
    else:
        form = FamilyMemberForm(instance=member)

    return render(request, 'barangay/edit_member.html', {
        'form': form,
        'member': member
    })

# ----------------- RFID Scan and Monitoring View -----------------
# ----------------- RFID Scan and Monitoring View -----------------
@login_required
@session_protected
def scan_rfid(request):
    if request.user.role not in ('MSWDO', 'BARANGAY'):
        return HttpResponseForbidden("Access Denied")

    error = None
    success = None
    family = None
    family_members = None

    now = timezone.now()

    # Get active schedule with assistance preloaded
    aid_schedule = AidSchedule.objects.select_related(
        'assistance',
        'assistance__program',
        'assistance__aid_category'
    ).filter(
        is_active=True,
        schedule_datetime__lte=now,
        end_datetime__gte=now,
    ).order_by('-schedule_datetime').first()

    if not aid_schedule:
        error = "No active aid schedule right now."
    elif not aid_schedule.assistance:
        error = "Active schedule has no assistance type configured. Please contact admin."

    # ----------------- Handle RFID SCAN -----------------
    if request.method == 'POST' and aid_schedule and aid_schedule.assistance:
        uid = request.POST.get('rfid_uid')
        member_id = request.POST.get('family_member')
        assistance = aid_schedule.assistance

        # Get family by RFID
        try:
            if request.user.role == 'BARANGAY':
                family = Family.objects.get(
                    rfid_uid=uid,
                    is_active=True,
                    household__barangay=request.user.barangay
                )
            else:
                family = Family.objects.get(rfid_uid=uid, is_active=True)
        except Family.DoesNotExist:
            error = "Invalid RFID UID."
            return render(request, 'accounts/scan_rfid.html', {'error': error, 'aid_schedule': aid_schedule})

        # -------- FAMILY-BASED assistance --------
        if assistance.beneficiary_type == 'family':
            already_claimed = AidClaim.objects.filter(
                family=family,
                assistance=assistance,
                schedule=aid_schedule
            ).exists()

            if already_claimed:
                error = f"{family.family_name} has already claimed {assistance.aid_category.name} for this schedule."
            else:
                AidClaim.objects.create(
                    family=family,
                    assistance=assistance,
                    schedule=aid_schedule,
                    created_by=request.user,
                )
                success = f"{family.family_name} successfully claimed {assistance.aid_category.name}."

        # -------- INDIVIDUAL-BASED assistance --------
        elif assistance.beneficiary_type == 'individual':
            # Get already claimed member IDs for this schedule
            claimed_member_ids = AidClaim.objects.filter(
                family=family,
                assistance=assistance,
                schedule=aid_schedule,
                family_member__isnull=False
            ).values_list('family_member_id', flat=True)

            # Build eligible members queryset
            eligible_members = family.members.exclude(id__in=claimed_member_ids)

            # Apply minimum age filter if configured on this assistance
            if assistance.minimum_age:
                eligible_members = eligible_members.filter(age__gte=assistance.minimum_age)

            if member_id:
                # A member was selected — process the claim
                member = get_object_or_404(FamilyMember, id=member_id, family=family)

                already_claimed = AidClaim.objects.filter(
                    family=family,
                    family_member=member,
                    assistance=assistance,
                    schedule=aid_schedule
                ).exists()

                if already_claimed:
                    error = f"{member.first_name} {member.last_name} already claimed {assistance.aid_category.name} for this schedule."
                else:
                    AidClaim.objects.create(
                        family=family,
                        family_member=member,
                        assistance=assistance,
                        schedule=aid_schedule,
                        created_by=request.user,
                    )
                    success = f"{member.first_name} {member.last_name} successfully claimed {assistance.aid_category.name}."
                    eligible_members = None

            else:
                # No member selected yet — show member selection step
                if not eligible_members.exists():
                    error = f"All eligible members have already claimed {assistance.aid_category.name} for this schedule."
                else:
                    return render(request, 'accounts/scan_rfid.html', {
                        'family': family,
                        'family_members': eligible_members,
                        'assistance': assistance,
                        'aid_schedule': aid_schedule,
                        'rfid_uid_value': uid,
                    })

            family_members = eligible_members if 'eligible_members' in dir() else None

    # ----------------- FILTERS (GET) -----------------
    selected_barangay = request.GET.get('barangay')

    claims = AidClaim.objects.select_related(
        'family',
        'family__household',
        'family__household__zone',
        'family__household__barangay',
        'family_member',
        'assistance',
        'assistance__aid_category',
        'assistance__program',
    )

    if aid_schedule:
        claims = claims.filter(schedule=aid_schedule)

    if selected_barangay:
        claims = claims.filter(family__household__barangay__id=selected_barangay)

    recent_claims = claims.order_by('-claimed_at')[:20]
    barangays = Barangay.objects.all()

    return render(request, 'accounts/scan_rfid.html', {
        'error': error,
        'success': success,
        'family': family,
        'family_members': family_members,
        'assistance': aid_schedule.assistance if aid_schedule and aid_schedule.assistance else None,
        'recent_claims': recent_claims,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
        'aid_schedule': aid_schedule,
        'rfid_uid_value': '',
    })


#----------------- RFID Registration View -----------------
@login_required
@session_protected
def register_rfid(request, family_id=None):
    # MSWDO ONLY
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangays = Barangay.objects.all()
    households = Household.objects.select_related('barangay', 'zone').all()
    families = Family.objects.select_related('household').all()

    error = None
    success = None

    # If family_id is provided, get that specific family
    selected_family = None
    if family_id:
        selected_family = get_object_or_404(Family, id=family_id)

    if request.method == 'POST':
        # If family_id is passed in POST (from form) or via URL
        fid = request.POST.get('family') or family_id
        rfid_uid = request.POST.get('rfid_uid')

        if not fid or not rfid_uid:
            error = "Please select a family and scan an RFID card."
        else:
            family = get_object_or_404(Family, id=fid)

            # Check if RFID already exists
            existing = Family.objects.filter(
                rfid_uid=rfid_uid
            ).exclude(id=family.id).first()

            if existing:
                error = f"RFID already assigned to {existing.family_name}."
            else:
                family.rfid_uid = rfid_uid
                family.save()
                success = f"RFID successfully registered to {family.family_name}."

    context = {
        'barangays': barangays,
        'households': households,
        'families': families,
        'selected_family': selected_family,  # used in template to show family name if editing
        'error': error,
        'success': success,
        'requires_auth': True,
    }

    return render(request, 'accounts/register_rfid.html', context)





#----------------MSWDO Navigation Views------------------
@login_required
@session_protected
def household_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    households = Household.objects.all()
    return render(request, 'accounts/household_list.html', {'households': households})

@login_required
@session_protected
def family_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    families = Family.objects.all()
    return render(request, 'accounts/family_list.html', {'families': families})

@login_required
@session_protected
def rfid_overview(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    total_rfid = Household.objects.count()
    claimed = AidClaim.objects.filter(claimed_at__isnull=False).count()
    unclaimed = total_rfid - claimed
    return render(request, 'accounts/rfid_overview.html', {
        'rfid_claimed': claimed,
        'rfid_unclaimed': unclaimed
    })

# ----------------- Program/Assistance Monitoring View -----------------
@login_required
@session_protected
def aid_type_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    programs = Program.objects.prefetch_related(
        'assistances__aid_category'
    ).filter(is_active=True)

    return render(request, 'accounts/aid_type_list.html', {
        'programs': programs,
    })

# ----------------- Aid Barangay List View -----------------
@login_required
@session_protected
def aid_barangay_list(request, assistance_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(
        Assistance.objects.select_related('program', 'aid_category'),
        id=assistance_id
    )
    barangays = Barangay.objects.all()

    return render(request, 'accounts/aid_barangay_list.html', {
        'assistance': assistance,
        'barangays': barangays,
    })


# ----------------- Aid Barangay Detail View -----------------
@login_required
@session_protected
def aid_barangay_detail(request, assistance_id, barangay_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(
        Assistance.objects.select_related('program', 'aid_category'),
        id=assistance_id
    )
    barangay = get_object_or_404(Barangay, id=barangay_id)

    families = Family.objects.filter(
        household__barangay=barangay,
        is_active=True
    ).select_related('household', 'household__zone')

    claims = AidClaim.objects.filter(
        assistance=assistance,
        family__household__barangay=barangay
    ).select_related('family', 'family_member')

    # Zone filter
    selected_zone = request.GET.get('zone')
    if selected_zone:
        families = families.filter(household__zone_id=selected_zone)

    # Date filter
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            claims = claims.filter(claimed_at__date=selected_date)
        except (ValueError):
            selected_date = None

    zones = Zone.objects.filter(barangay=barangay)
    claim_map = {claim.family_id: claim for claim in claims}

    families_data = []
    for family in families:
        claim = claim_map.get(family.id)
        if claim:
            claimed_by_name = (
                f"{claim.family_member.first_name} {claim.family_member.last_name}"
                if claim.family_member else "FAMILY (RFID)"
            )
            status = f"CLAIMED BY: {claimed_by_name} on {claim.claimed_at.strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            status = "NOT CLAIMED"

        families_data.append({
            'household_address': family.household.address,
            'family_name': family.family_name,
            'status': status,
            'zone': family.household.zone.name if family.household.zone else "N/A"
        })

    total_families = len(families_data)
    claimed_count = sum(1 for f in families_data if f['status'].startswith("CLAIMED"))
    unclaimed_count = total_families - claimed_count
    progress_percent = int((claimed_count / total_families) * 100) if total_families else 0

    zone_stats = []
    for zone in zones:
        zone_families = [f for f in families_data if f['zone'] == zone.name]
        total = len(zone_families)
        claimed = sum(1 for f in zone_families if f['status'].startswith("CLAIMED"))
        percent = int((claimed / total) * 100) if total else 0
        zone_stats.append({
            'zone': zone.name,
            'claimed': claimed,
            'total': total,
            'percent': percent
        })

    return render(request, 'accounts/aid_barangay_detail.html', {
        'assistance': assistance,
        'barangay': barangay,
        'families_data': families_data,
        'zones': zones,
        'zone_stats': zone_stats,
        'selected_zone': selected_zone,
        'selected_date': selected_date,
        'total_families': total_families,
        'claimed_count': claimed_count,
        'unclaimed_count': unclaimed_count,
        'progress_percent': progress_percent,
    })

#---------------- RFID Claim Monitoring View -----------------
@login_required
@session_protected
def rfid_claim_monitoring(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    claims = AidClaim.objects.select_related(
        'family',
        'family__household',
        'family__household__zone',
        'family__household__barangay',
        'family_member',
        'created_by'  # ADD this so it doesn't do extra queries
    ).order_by('-claimed_at')

    monitoring_data = []
    for claim in claims:
        monitoring_data.append({
            'rfid_uid': claim.family.rfid_uid,
            'family_name': claim.family.family_name,
            'member_name': (
                f"{claim.family_member.first_name} {claim.family_member.last_name}"
                if claim.family_member else "ALL MEMBERS"
            ),
            'address': claim.family.household.address,
            'aid_type': claim.aid_type,
            'claimed_at': claim.claimed_at,
            'processed_by': (
                claim.created_by.username
                if claim.created_by else "System"
            ),
        })

    return render(request, 'accounts/rfid_claim_monitoring.html', {
        'claims': monitoring_data
    })

#---------------- RFID Live Claims JSON View -----------------
@login_required
@session_protected
def rfid_live_claims(request):
    now = timezone.now()

    today_aid = AidSchedule.objects.select_related('assistance').filter(
        schedule_datetime__lte=now,
        is_active=True
    ).order_by('-schedule_datetime').first()

    claims = AidClaim.objects.select_related(
        'family',
        'family_member',
        'family__household',
        'family__household__barangay',
        'assistance',
        'assistance__aid_category',
    )

    if today_aid:
        claims = claims.filter(schedule=today_aid)

    if request.user.role == 'BARANGAY':
        claims = claims.filter(
            family__household__barangay=request.user.barangay
        )

    data = []
    for c in claims:
        data.append({
            'id': c.id,
            'rfid_uid': c.family.rfid_uid,
            'family_name': c.family.family_name,
            'family_member_name': (
                f"{c.family_member.first_name} {c.family_member.last_name}"
                if c.family_member else None
            ),
            'address': c.family.household.address,
            # NEW: use assistance label
            'aid_type': str(c.assistance) if c.assistance else (c.aid_type or 'N/A'),
            'claimed_at': c.claimed_at.strftime('%Y-%m-%d %H:%M:%S'),
            'barangay_id': c.family.household.barangay.id,
        })

    return JsonResponse({'claims': data})

#---------------- Get Family Members for Aid Claiming (AJAX) -----------------
@login_required
@session_protected
def get_family_members(request):
    uid = request.GET.get('rfid_uid')
    assistance_id = request.GET.get('assistance_id')  # NEW: receive assistance ID

    try:
        family = Family.objects.get(rfid_uid=uid, is_active=True)
    except Family.DoesNotExist:
        return JsonResponse({'members': []})

    try:
        assistance = Assistance.objects.get(id=assistance_id)
    except Assistance.DoesNotExist:
        return JsonResponse({'members': []})

    # Exclude already claimed members for this assistance
    claimed_member_ids = AidClaim.objects.filter(
        family=family,
        assistance=assistance,
        family_member__isnull=False
    ).values_list('family_member_id', flat=True)

    members = family.members.exclude(id__in=claimed_member_ids)

    # Apply minimum age if set on this assistance
    if assistance.minimum_age:
        members = members.filter(age__gte=assistance.minimum_age)

    members_data = [
        {'id': m.id, 'name': f'{m.first_name} {m.last_name}'}
        for m in members
    ]
    return JsonResponse({'members': members_data})

#----------------- Set Aid Schedule View -----------------
@login_required
@session_protected
def set_aid_schedule(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        # NEW: receive assistance ID instead of aid_type string
        assistance_id = request.POST.get('assistance')
        assistance = Assistance.objects.filter(id=assistance_id).first()

        if not assistance:
            messages.error(request, "Please select a valid assistance type.")
            return redirect('mswdo_dashboard')

        start = parse_datetime(request.POST.get('schedule_datetime'))
        end = parse_datetime(request.POST.get('end_datetime'))

        if not start or not end:
            messages.error(request, "Invalid date/time format. Please try again.")
            return redirect('mswdo_dashboard')

        if timezone.is_naive(start):
            start = timezone.make_aware(start)

        if timezone.is_naive(end):
            end = timezone.make_aware(end)

        if end <= start:
            messages.error(request, "End date & time must be after the start date & time.")
            return redirect('mswdo_dashboard')

        location = request.POST.get('location')
        barangay_id = request.POST.get('barangay')
        barangay = Barangay.objects.filter(id=barangay_id).first() if barangay_id else None

        # Auto-expire past schedules
        AidSchedule.objects.filter(
            end_datetime__lt=timezone.now()
        ).update(is_active=False)

        AidSchedule.objects.create(
            assistance=assistance,       # NEW
            schedule_datetime=start,
            end_datetime=end,
            location=location,
            barangay=barangay
        )

        messages.success(request, f"Distribution scheduled successfully: {assistance}")

    return redirect('mswdo_dashboard')
#------------------ For MSWDO Household List and RFID -----------------
@login_required
@session_protected
def barangay_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangays = Barangay.objects.all().order_by('name')

    return render(request, 'accounts/barangay_list.html', {
        'barangays': barangays,
    })

@login_required
@session_protected
def barangay_zones(request, barangay_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = get_object_or_404(Barangay, id=barangay_id)
    zones = Zone.objects.filter(barangay=barangay).order_by('name')

    return render(request, 'accounts/barangay_zones.html', {
        'barangay': barangay,
        'zones': zones,
    })

@login_required
@session_protected
def zone_households(request, zone_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(
        Zone.objects.select_related('barangay'),
        id=zone_id
    )

    households = Household.objects.filter(
        zone=zone
    ).order_by('house_number')

    return render(request, 'accounts/zone_households.html', {
        'zone': zone,
        'barangay': zone.barangay,
        'households': households,
    })

@login_required
@session_protected
def household_info(request, household_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    household = get_object_or_404(
        Household.objects.select_related('zone', 'barangay'),
        id=household_id
    )

    # Get all active families in the household
    families = Family.objects.filter(
        household=household,
        is_active=True
    ).order_by('family_name')

    return render(request, 'accounts/household_info.html', {
        'household': household,
        'families': families,
    })

@login_required
@session_protected
def family_members(request, family_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(Family.objects.select_related('household', 'household__zone', 'household__barangay'), id=family_id)

    members = family.members.all().order_by('first_name', 'last_name')  # or use select_related if needed

    return render(request, 'accounts/family_members.html', {
        'family': family,
        'members': members,
    })

@login_required
@session_protected
def deactivate_rfid(request, family_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(Family, id=family_id)

    if family.rfid_uid:
        old_rfid = family.rfid_uid
        family.rfid_uid = None
        family.save()
        messages.success(request, f"RFID {old_rfid} deactivated for {family.family_name}.")
    else:
        messages.warning(request, f"{family.family_name} does not have an RFID to deactivate.")

    return redirect('household_info', household_id=family.household.id)


#----------------- Analytics View -----------------
@login_required
@session_protected
def analytics(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    # Group by assistance → aid_category name
    aid_data = (
        AidClaim.objects
        .filter(assistance__isnull=False)
        .values('assistance__aid_category__name', 'assistance__program__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    labels = [
        f"{item['assistance__program__name']} › {item['assistance__aid_category__name']}"
        for item in aid_data
    ]
    data = [item['count'] for item in aid_data]

    return render(request, 'accounts/analytics.html', {
        'labels': labels,
        'data': data,
    })

#----------------- Barangay Analytics View -----------------
@login_required
@session_protected
def barangay_analytics(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay = request.user.barangay

    aid_data = (
        AidClaim.objects
        .filter(
            family__household__barangay=barangay,
            assistance__isnull=False
        )
        .values('assistance__aid_category__name', 'assistance__program__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    labels = [
        f"{item['assistance__program__name']} › {item['assistance__aid_category__name']}"
        for item in aid_data
    ]
    data = [item['count'] for item in aid_data]

    total_families = Family.objects.filter(
        household__barangay=barangay,
        is_active=True
    ).count()

    claimed_families = AidClaim.objects.filter(
        family__household__barangay=barangay
    ).values('family').distinct().count()

    return render(request, 'barangay/barangay_analytics.html', {
        'labels': labels,
        'data': data,
        'barangay': barangay,
        'total_families': total_families,
        'claimed_families': claimed_families,
    })

#----------------- Aid Schedule Reports View -----------------
@login_required
@session_protected
def aid_reports(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    selected_barangay = request.GET.get('barangay')

    schedules = AidSchedule.objects.all().order_by('-schedule_datetime')

    if selected_barangay:
        schedules = schedules.filter(barangay_id=selected_barangay)

    # Attach claims per schedule
    for sched in schedules:
        sched.claims = AidClaim.objects.filter(
            schedule=sched          #filter by schedule directly
        ).select_related(
            'family',
            'family_member',
            'family__household',
            'family__household__barangay',
            'assistance',
            'assistance__aid_category',
        )

    barangays = Barangay.objects.all()

    return render(request, 'accounts/aid_reports.html', {
        'schedules': schedules,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
        'now': timezone.now(),
    })

#----------------- OTP Verification View -----------------
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

#----------------- Aid Schedule Status API View -----------------
@login_required
@session_protected
def schedule_status(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    now = timezone.localtime(timezone.now())

    # Auto-deactivate expired schedules
    AidSchedule.objects.filter(
        end_datetime__lt=now, is_active=True
    ).update(is_active=False)

    active = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        end_datetime__gte=now,
        is_active=True
    )
    upcoming = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_active=True
    )
    expired = AidSchedule.objects.filter(
        end_datetime__lt=now
    )

    def fmt(dt):
        return timezone.localtime(dt).strftime('%B %d, %Y, %I:%M %p') if dt else None

    def serialize(qs):
        return [{
            'id': s.id,
            # NEW: use assistance label instead of aid_type string
            'aid_type': str(s.assistance) if s.assistance else (s.aid_type or 'N/A'),
            'schedule_datetime': fmt(s.schedule_datetime),
            'end_datetime': fmt(s.end_datetime),
            'location': s.location,
            'barangay': str(s.barangay) if s.barangay else 'All Barangays',
        } for s in qs]

    return JsonResponse({
        'active': serialize(active),
        'upcoming': serialize(upcoming),
        'expired': serialize(expired),
    })
# ----------------- Program Management Views -----------------
#----------------- Program List View -----------------
@login_required
@session_protected
def program_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    programs = Program.objects.prefetch_related(
        'aid_categories',
        'assistances__aid_category'
    ).all().order_by('name')

    return render(request, 'accounts/program_list.html', {
        'programs': programs,
    })

#----------------- Add Program View -----------------
@login_required
@session_protected
def add_program(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = ProgramForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Program added successfully.")
            return redirect('program_list')
    else:
        form = ProgramForm()

    return render(request, 'accounts/add_program.html', {'form': form})

#----------------- Toggle Program Active/Inactive -----------------
@login_required
@session_protected
def edit_program(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)

    if request.method == 'POST':
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, f"Program '{program.name}' updated successfully.")
            return redirect('program_list')
    else:
        form = ProgramForm(instance=program)

    return render(request, 'accounts/edit_program.html', {
        'form': form,
        'program': program,
    })

#----------------- Toggle Program Active/Inactive -----------------
@login_required
@session_protected
def toggle_program(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)
    program.is_active = not program.is_active
    program.save()

    status = "activated" if program.is_active else "deactivated"
    messages.success(request, f"Program '{program.name}' {status}.")
    return redirect('program_list')

#----------------- Add Aid Category to Program View -----------------
@login_required
@session_protected
def add_aid_category(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)

    if request.method == 'POST':
        form = AidCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Aid category added successfully.")
            return redirect('program_list')
    else:
        form = AidCategoryForm(initial={'program': program})

    return render(request, 'accounts/add_aid_category.html', {
        'form': form,
        'program': program,
    })

#----------------- Add Assistance View -----------------
@login_required
@session_protected
def add_assistance(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = AssistanceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Assistance entry added successfully.")
            return redirect('program_list')
    else:
        form = AssistanceForm()

    return render(request, 'accounts/add_assistance.html', {'form': form})

#----------------- Toggle Assistance Active/Inactive -----------------
@login_required
@session_protected
def toggle_assistance(request, assistance_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(Assistance, id=assistance_id)
    assistance.is_active = not assistance.is_active
    assistance.save()

    status = "activated" if assistance.is_active else "deactivated"
    messages.success(request, f"Assistance '{assistance}' {status}.")
    return redirect('program_list')


# ----------------- AJAX: Get Aid Categories by Program -----------------
@login_required
@session_protected
def get_aid_categories(request):
    program_id = request.GET.get('program_id')
    categories = AidCategory.objects.filter(
        program_id=program_id,
        is_active=True
    ).values('id', 'name')
    return JsonResponse({'categories': list(categories)})

#----------------- Edit Assistance View -----------------
@login_required
@session_protected
def edit_assistance(request, assistance_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(
        Assistance.objects.select_related('program', 'aid_category'),
        id=assistance_id
    )

    if request.method == 'POST':
        program_id     = request.POST.get('program')
        aid_category_id = request.POST.get('aid_category')
        beneficiary_type = request.POST.get('beneficiary_type')
        minimum_age    = request.POST.get('minimum_age') or None
        is_active      = request.POST.get('is_active') == 'on'

        # Validate
        if not all([program_id, aid_category_id, beneficiary_type]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('program_list')

        try:
            aid_category = AidCategory.objects.get(
                id=aid_category_id,
                program_id=program_id
            )
        except AidCategory.DoesNotExist:
            messages.error(request, "Invalid category for the selected program.")
            return redirect('program_list')

        assistance.aid_category      = aid_category
        assistance.program_id        = program_id
        assistance.beneficiary_type  = beneficiary_type
        assistance.minimum_age       = minimum_age
        assistance.is_active         = is_active
        assistance.save()

        messages.success(request, f"Assistance '{assistance}' updated successfully.")

    return redirect('program_list')