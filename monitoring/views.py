
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

from accounts.decorators import session_protected, mswdo_or_staff_required
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AidClaim

from accounts.forms import UserEditForm, UserInvitationForm
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm
from programs.forms import ProgramForm, AidCategoryForm, AssistanceForm
# from distribution.forms import AidScheduleForm  # if any

from django.utils.safestring import mark_safe
from distribution.services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from django.urls import reverse
from django.core.cache import cache
import json

User = get_user_model()


@login_required
@session_protected
@mswdo_or_staff_required
def aid_type_list(request):

    programs = Program.objects.prefetch_related(
        'assistances__aid_category'
    ).filter(is_active=True)

    return render(request, 'monitoring/aid_type_list.html', {
        'programs': programs,
    })


@login_required
@session_protected
@mswdo_or_staff_required
def aid_barangay_list(request, assistance_id):

    assistance = get_object_or_404(
        Assistance.objects.select_related('program', 'aid_category'),
        id=assistance_id
    )
    barangays = Barangay.objects.all()

    return render(request, 'monitoring/aid_barangay_list.html', {
        'assistance': assistance,
        'barangays': barangays,
    })


@login_required
@session_protected
@mswdo_or_staff_required
def aid_barangay_detail(request, assistance_id, barangay_id):

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

    return render(request, 'monitoring/aid_barangay_detail.html', {
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


@login_required
@session_protected
@mswdo_or_staff_required
def rfid_claim_monitoring(request):

    claims = AidClaim.objects.select_related(
        'family',
        'family__household',
        'family__household__zone',
        'family__household__barangay',
        'family_member',
        'created_by' 
    ).order_by('-claimed_at')

    is_staff_scoped = (request.user.role == 'MSWDO_STAFF')
    if is_staff_scoped:
        claims = claims.filter(created_by=request.user)

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
            'aid_type': str(claim.assistance) if claim.assistance else 'N/A',
            'claimed_at': claim.claimed_at,
            'processed_by': (
                claim.created_by.username
                if claim.created_by else "System"
            ),
        })

    return render(request, 'monitoring/rfid_claim_monitoring.html', {
        'claims': monitoring_data,
        'is_staff_scoped': is_staff_scoped
    })


@login_required
@session_protected
def rfid_live_claims(request):
    # Notice: Intentionally NOT applying @mswdo_or_staff_required here 
    # because BARANGAY role also needs access to this endpoint as seen below.
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
    elif request.user.role == 'MSWDO_STAFF':
        claims = claims.filter(created_by=request.user)

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

    if assistance.minimum_age:
        today = date.today()
        try:
            threshold_date = today.replace(year=today.year - assistance.minimum_age)
        except ValueError:
            threshold_date = today.replace(year=today.year - assistance.minimum_age, day=28)
        members = members.filter(birthdate__lte=threshold_date)

    members_data = [
        {'id': m.id, 'name': f'{m.first_name} {m.last_name}'}
        for m in members
    ]
    return JsonResponse({'members': members_data})


@login_required
@session_protected
def get_aid_categories(request):
    program_id = request.GET.get('program_id')
    categories = AidCategory.objects.filter(
        program_id=program_id,
        is_active=True
    ).values('id', 'name')
    return JsonResponse({'categories': list(categories)})


@login_required
@session_protected
@mswdo_or_staff_required
def schedule_status(request):

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
            'iso_datetime': s.schedule_datetime.isoformat() if s.schedule_datetime else None,
            'end_datetime': fmt(s.end_datetime),
            'location': s.location,
            'barangay': str(s.barangay) if s.barangay else 'All Barangays',
        } for s in qs]

    return JsonResponse({
        'active': serialize(active),
        'upcoming': serialize(upcoming),
        'expired': serialize(expired),
    })


@login_required
@session_protected
@mswdo_or_staff_required
def analytics(request):

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

    return render(request, 'monitoring/analytics.html', {
        'labels': labels,
        'data': data,
    })


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

    return render(request, 'monitoring/barangay_analytics.html', {
        'labels': labels,
        'data': data,
        'barangay': barangay,
        'total_families': total_families,
        'claimed_families': claimed_families,
    })


@login_required(login_url='login')
@session_protected
def barangay_schedule_status(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay_obj = request.user.barangay
    now = timezone.localtime(timezone.now())

    # Auto-deactivate expired schedules
    AidSchedule.objects.filter(
        end_datetime__lt=now, is_active=True
    ).update(is_active=False)

    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        end_datetime__gte=now,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    ).select_related('assistance', 'assistance__program', 'assistance__aid_category', 'barangay')

    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    ).select_related('assistance', 'assistance__program', 'assistance__aid_category', 'barangay')

    def fmt(dt):
        return timezone.localtime(dt).strftime('%B %d, %Y, %I:%M %p') if dt else None

    def serialize(qs):
        return [{
            'id': s.id,
            'aid_label': str(s.assistance) if s.assistance else 'N/A',
            'beneficiary_type': s.assistance.beneficiary_type if s.assistance else None,
            'schedule_datetime': fmt(s.schedule_datetime),
            'iso_datetime': s.schedule_datetime.isoformat() if s.schedule_datetime else None,
            'end_datetime': fmt(s.end_datetime),
            'location': s.location,
            'barangay': str(s.barangay) if s.barangay else 'All Barangays',
        } for s in qs]

    return JsonResponse({
        'active': serialize(active_schedules),
        'upcoming': serialize(upcoming_schedules),
    })


