from urllib import request
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Count, Q

from accounts.decorators import session_protected
from .models import AidSchedule, User, Household, Zone, Family, FamilyMember, Barangay, AidClaim, AidType
from .forms import BarangayAdminEditForm, HouseholdForm, FamilyForm, FamilyMemberForm, BarangayAdminForm
from django.utils.safestring import mark_safe
from .services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django.urls import reverse
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
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, "Account is deactivated.")
            else:
                login(request, user)
                if user.role == 'MSWDO':
                    response = redirect('mswdo_dashboard')
                else:
                    response = redirect('barangay_dashboard')

                # ✅ Set a JS-readable cookie to signal active session
                response.set_cookie('sara_auth', '1', samesite='Lax')
                return response
        else:
            messages.error(request, "Invalid username or password.")

    # ✅ Prevent login page from being stored in bfcache
    response = render(request, 'accounts/login.html')
    response['Cache-Control'] = 'no-store'
    return response

User = get_user_model()

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

    # Add this for template iteration
    aid_types = [choice[0] for choice in AidType.choices]

    #today = date.today()
    #aid_of_the_day = AidOfTheDay.objects.filter(date=today).first()

    #schedules = AidSchedule.objects.all().order_by('-schedule_datetime')

    now = timezone.localtime(timezone.now())
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


    context = {
        'barangays': barangays,
        'barangay_accounts': barangay_accounts,  # For table
        'barangay_count': barangay_count,
        'household_count': household_count,
        'family_count': family_count,
        'rfid_claimed': rfid_claimed,
        'rfid_unclaimed': rfid_unclaimed,
        'aid_types': aid_types,  # <-- added this
       
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

    barangay = User.objects.get(id=user_id)
    barangay.is_active = False
    barangay.save()
    
    return redirect('barangay_accounts')

# ── Activate Barangay ─────────────────────────────────────────
@login_required(login_url='login')
@session_protected
def activate_barangay(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = User.objects.get(id=user_id)
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
    error = None
    success = None
    family = None
    family_members = None
    aid_type = None

    # Get today's aid schedule (if any)
    now = timezone.now()

    aid_schedule = AidSchedule.objects.filter(
        is_active=True
    ).order_by('-schedule_datetime').first()

    if not aid_schedule:
        error = "No active aid schedule right now."

    # ----------------- Handle RFID SCAN -----------------
    if request.method == 'POST':
        uid = request.POST.get('rfid_uid')
        member_id = request.POST.get('family_member')

        # If AidOfTheDay exists, force aid_type
        if aid_schedule:
            aid_type = aid_schedule.aid_type
        else:
            error = "Today's aid type has not been set. Please contact admin."
            return render(request, 'accounts/scan_rfid.html', {
                'error': error
            })

        # Get family by RFID
        try:
            family = Family.objects.get(rfid_uid=uid, is_active=True)
        except Family.DoesNotExist:
            error = "Invalid RFID UID."
            return render(request, 'accounts/scan_rfid.html', {
                'error': error
            })

        # -------- RELIEF (family-based) --------
        if aid_type == 'RELIEF':
            if AidClaim.objects.filter(family=family, aid_type=aid_type).exists():
                error = f"{family.family_name} has already claimed RELIEF."
            else:
                AidClaim.objects.create(
                    family=family,
                    aid_type=aid_type,
                    schedule=aid_schedule,
                )
                success = f"{family.family_name} successfully claimed RELIEF."

        # -------- SENIOR (individual-based) --------
        elif aid_type == 'SENIOR':
            claimed_member_ids = AidClaim.objects.filter(
                family=family,
                aid_type=aid_type,
                family_member__isnull=False
            ).values_list('family_member_id', flat=True)

            family_members = family.members.filter(
                age__gte=60
            ).exclude(id__in=claimed_member_ids)

            # If member_id is submitted, create claim
            if member_id:
                member = get_object_or_404(
                    FamilyMember,
                    id=member_id,
                    family=family
                )
                if AidClaim.objects.filter(
                    family=family,
                    family_member=member,
                    aid_type=aid_type
                ).exists():
                    error = f"{member.first_name} {member.last_name} already claimed {aid_type}."
                else:
                    AidClaim.objects.create(
                        family=family,
                        family_member=member,
                        aid_type=aid_type,
                        claimed_at=timezone.now()
                    )
                    success = f"{member.first_name} {member.last_name} successfully claimed {aid_type}."
                    # Clear family_members after claim so dropdown doesn't persist
                    family_members = None
            else:
                # Show dropdown if eligible members exist
                if not family_members.exists():
                    error = f"All eligible members have already claimed {aid_type}."
                else:
                    return render(request, 'accounts/scan_rfid.html', {
                        'family': family,
                        'family_members': family_members,
                        'aid_type': aid_type,
                        'aid_of_the_day': aid_schedule,
                        'rfid_uid_value': ''  # clear RFID input
                    })

    # ----------------- FILTERS (GET) -----------------
    selected_barangay = request.GET.get('barangay')
    claims = AidClaim.objects.select_related(
        'family',
        'family__household',
        'family__household__zone',
        'family__household__barangay',
        'family_member'
    )

    if selected_barangay:
        claims = claims.filter(family__household__barangay__id=selected_barangay)

    recent_claims = claims.order_by('-claimed_at')[:20]
    barangays = Barangay.objects.all()

    # ----------------- Prepare RFID input value -----------------
    rfid_uid_value = ''  # Always clear after submission

    return render(request, 'accounts/scan_rfid.html', {
        'error': error,
        'success': success,
        'family': family,
        'family_members': family_members,
        'aid_type': aid_type,
        'recent_claims': recent_claims,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
        'aid_schedule': aid_schedule,
        'rfid_uid_value': rfid_uid_value,
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

#----------------- Aid Type/Monitoring Views -----------------
@login_required
@session_protected
def aid_type_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    return render(request, 'accounts/aid_type_list.html', {
        'aid_types': AidType.choices
    })

@login_required
@session_protected
def aid_barangay_list(request, aid_type):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangays = Barangay.objects.all()

    return render(request, 'accounts/aid_barangay_list.html', {
        'aid_type': aid_type,
        'barangays': barangays
    })

#------------------ Aid Barangay Detail View -----------------
@login_required
@session_protected
def aid_barangay_detail(request, aid_type, barangay_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = get_object_or_404(Barangay, id=barangay_id)

    families = Family.objects.filter(
        household__barangay=barangay,
        is_active=True
    ).select_related(
        'household',
        'household__zone'
    )

    claims = AidClaim.objects.filter(
        aid_type=aid_type,
        family__household__barangay=barangay
    ).select_related('family', 'family_member')

    # ---------------- ZONE FILTER ----------------
    selected_zone = request.GET.get('zone')
    if selected_zone:
        families = families.filter(household__zone_id=selected_zone)

    # ---------------- DATE FILTER (RELIEF DAY) ----------------
    selected_date = request.GET.get('date')
    if selected_date:
        claims = claims.filter(claimed_at__date=selected_date)

    zones = Zone.objects.filter(barangay=barangay)

    # Map family_id → AidClaim
    claim_map = {claim.family_id: claim for claim in claims}

    # ---------------- BUILD TABLE DATA ----------------
    families_data = []
    for family in families:
        claim = claim_map.get(family.id)

        if claim:
            if claim.family_member:
                claimed_by_name = (
                    f"{claim.family_member.first_name} "
                    f"{claim.family_member.last_name}"
                )
            else:
                claimed_by_name = "FAMILY (RFID)"

            status = (
                f"CLAIMED BY: {claimed_by_name} "
                f"on {claim.claimed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            status = "NOT CLAIMED"

        families_data.append({
            'household_address': family.household.address,
            'family_name': family.family_name,
            'status': status,
            'zone': family.household.zone.name if family.household.zone else "N/A"
        })

    # ---------------- COUNTS (FIXED) ----------------
    total_families = len(families_data)
    claimed_count = sum(
        1 for f in families_data if f['status'].startswith("CLAIMED")
    )
    unclaimed_count = total_families - claimed_count
    progress_percent = int(
        (claimed_count / total_families) * 100
    ) if total_families else 0

    # ---------------- PER-ZONE PROGRESS ----------------
    zone_stats = []
    for zone in zones:
        zone_families = [
            f for f in families_data if f['zone'] == zone.name
        ]
        total = len(zone_families)
        claimed = sum(
            1 for f in zone_families if f['status'].startswith("CLAIMED")
        )
        percent = int((claimed / total) * 100) if total else 0

        zone_stats.append({
            'zone': zone.name,
            'claimed': claimed,
            'total': total,
            'percent': percent
        })

    return render(request, 'accounts/aid_barangay_detail.html', {
        'aid_type': aid_type,
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


#------------------ Aid List Views -----------------
@login_required
@session_protected
def aid_list(request, aid_type):
    barangays = Barangay.objects.all()
    return render(request, 'accounts/aid_list.html', {
        'aid_type': aid_type,
        'barangays': barangays
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
        'family_member'
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
            'claimed_at': claim.claimed_at
        })

    return render(request, 'accounts/rfid_claim_monitoring.html', {
        'claims': monitoring_data
    })

#---------------- RFID Live Claims JSON View -----------------
@login_required
@session_protected
def rfid_live_claims(request):
    now = timezone.now()

    today_aid = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_active=True
    ).order_by('-schedule_datetime').first()

    aid_type = today_aid.aid_type if today_aid else None

    claims = AidClaim.objects.filter(
        aid_type=aid_type
    ).select_related('family', 'family_member', 'family__household', 'family__household__barangay')

    data = []
    for c in claims:
        data.append({
            'id': c.id,
            'rfid_uid': c.family.rfid_uid,
            'family_name': c.family.family_name,
            'family_member_name': f"{c.family_member.first_name} {c.family_member.last_name}" if c.family_member else None,
            'address': c.family.household.address,
            'aid_type': c.aid_type,
            'claimed_at': c.claimed_at.strftime('%Y-%m-%d %H:%M:%S'),
            'barangay_id': c.family.household.barangay.id,
        })

    return JsonResponse({'claims': data})


@login_required
@session_protected
def get_family_members(request):
    uid = request.GET.get('rfid_uid')
    aid_type = request.GET.get('aid_type')
    try:
        family = Family.objects.get(rfid_uid=uid, is_active=True)
    except Family.DoesNotExist:
        return JsonResponse({'members': []})

    claimed_member_ids = AidClaim.objects.filter(
        family=family,
        aid_type=aid_type,
        family_member__isnull=False
    ).values_list('family_member_id', flat=True)

    if aid_type == 'SENIOR':
        members = family.members.filter(age__gte=60).exclude(id__in=claimed_member_ids)
    else:
        members = family.members.exclude(id__in=claimed_member_ids)

    members_data = [{'id': m.id, 'name': f'{m.first_name} {m.last_name}'} for m in members]
    return JsonResponse({'members': members_data})

#----------------- Set Aid Schedule View -----------------
@login_required
@session_protected
def set_aid_schedule(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        aid_type = request.POST.get('aid_type')

        start = parse_datetime(request.POST.get('schedule_datetime'))
        end = parse_datetime(request.POST.get('end_datetime'))

        # Guard against parse_datetime returning None
        if not start or not end:
            messages.error(request, "Invalid date/time format. Please try again.")
            return redirect('mswdo_dashboard')

        if timezone.is_naive(start):
            start = timezone.make_aware(start)

        if timezone.is_naive(end):
            end = timezone.make_aware(end)

        location = request.POST.get('location')
        barangay_id = request.POST.get('barangay')
        barangay = Barangay.objects.filter(id=barangay_id).first() if barangay_id else None

        AidSchedule.objects.create(
            aid_type=aid_type,
            schedule_datetime=start,
            end_datetime=end,
            location=location,
            barangay=barangay
        )

        messages.success(request, "Distribution scheduled successfully.")

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

    aid_data = AidClaim.objects.values('aid_type').annotate(count=Count('id'))

    labels = [item['aid_type'] for item in aid_data]
    data = [item['count'] for item in aid_data]

    return render(request, 'accounts/analytics.html', {
        'labels': mark_safe(json.dumps(labels)),
        'data': mark_safe(json.dumps(data)),
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
            aid_type=sched.aid_type,
            claimed_at__gte=sched.schedule_datetime,
            claimed_at__lte=sched.end_datetime
        ).select_related(
            'family',
            'family_member',
            'family__household',
            'family__household__barangay'
        )

    barangays = Barangay.objects.all()

    return render(request, 'accounts/aid_reports.html', {
        'schedules': schedules,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
    })