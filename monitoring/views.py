
from urllib import request
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date
from django.db.models import Count, Q, Sum

from accounts.decorators import session_protected, mswdo_or_staff_required
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AidClaim

from accounts.forms import CreateUserForm
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
from reports.analytics_utils import get_category_claims_data, get_age_bracket_index, AGE_BRACKETS

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

    # Auto-deactivate logic removed as is_finished handles completion manually or automatically.

    active = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    )
    upcoming = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_finished=False,
        is_active=True
    )
    expired = AidSchedule.objects.filter(
        is_finished=True
    )

    def fmt(dt):
        return timezone.localtime(dt).strftime('%B %d, %Y, %I:%M %p') if dt else None

    def serialize(qs):
        from distribution.services import is_staff_assigned_to_scan
        return [{
            'id': s.id,
            # NEW: use assistance label instead of aid_type string
            'aid_type': str(s.assistance) if s.assistance else (s.aid_type or 'N/A'),
            'schedule_datetime': fmt(s.schedule_datetime),
            'iso_datetime': s.schedule_datetime.isoformat() if s.schedule_datetime else None,
            'location': s.location,
            'barangay': str(s.barangay) if s.barangay else 'All Barangays',
            'finish_reason': s.finish_reason,
            'is_assigned_or_open': is_staff_assigned_to_scan(request.user, s) if request.user.role == 'MSWDO_STAFF' else True,
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
    # Render the template - data will be fetched via AJAX
    return render(request, 'monitoring/analytics.html')


@login_required
@session_protected
@mswdo_or_staff_required
def analytics_api(request):
    """
    Combined analytics API endpoint returning all data for the analytics dashboard.
    Filters: aid_category, program, barangay, gender, age_bracket, date_from, date_to
    """
    # Parse filters
    aid_category_id = request.GET.get('aid_category')
    program_id = request.GET.get('program')
    barangay_id = request.GET.get('barangay')
    gender = request.GET.get('gender')
    age_bracket = request.GET.get('age_bracket')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Base queryset
    claims_qs = AidClaim.objects.filter(assistance__isnull=False).select_related(
        'family', 'family_member', 'family__household', 'family__household__barangay',
        'assistance', 'assistance__aid_category', 'assistance__program'
    )
    
    # Apply filters
    if aid_category_id:
        claims_qs = claims_qs.filter(assistance__aid_category_id=aid_category_id)
    if program_id:
        claims_qs = claims_qs.filter(assistance__program_id=program_id)
    if barangay_id:
        claims_qs = claims_qs.filter(family__household__barangay_id=barangay_id)
    if date_from:
        try:
            from datetime import datetime
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            claims_qs = claims_qs.filter(claimed_at__gte=date_from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime, timedelta
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            claims_qs = claims_qs.filter(claimed_at__lt=date_to_dt)
        except ValueError:
            pass
    
    # Gender and age filters require member data
    if gender or age_bracket:
        claims_qs = claims_qs.filter(family_member__isnull=False)
        if gender:
            claims_qs = claims_qs.filter(family_member__sex=gender)
        if age_bracket:
            bracket_idx = int(age_bracket)
            bracket = AGE_BRACKETS[bracket_idx]
            min_age = bracket['min_age']
            max_age = bracket['max_age']
            if max_age is None:
                # 80+ bracket
                from datetime import date
                today = date.today()
                threshold_date = today.replace(year=today.year - min_age)
                claims_qs = claims_qs.filter(family_member__birthdate__lte=threshold_date)
            else:
                from datetime import date
                today = date.today()
                max_threshold = today.replace(year=today.year - min_age)
                min_threshold = today.replace(year=today.year - max_age - 1)
                claims_qs = claims_qs.filter(
                    family_member__birthdate__lte=max_threshold,
                    family_member__birthdate__gt=min_threshold
                )
    
    # --- KPIs ---
    total_claims = claims_qs.count()
    
    # Unique beneficiaries (family_member_id if individual, family_id if family-based)
    beneficiaries_set = set()
    for claim in claims_qs:
        if claim.family_member_id:
            beneficiaries_set.add(f"member_{claim.family_member_id}")
        else:
            beneficiaries_set.add(f"family_{claim.family_id}")
    unique_beneficiaries = len(beneficiaries_set)
    
    # Total Aid Released (scheduled distributions with amount only)
    scheduled_claims = claims_qs.filter(claim_type='DISTRIBUTION', amount__isnull=False)
    total_aid_released = scheduled_claims.aggregate(total=Sum('amount'))['total'] or 0
    
    # Walk-in claims count (for the note)
    walkin_count = claims_qs.filter(claim_type='WALK_IN').count()
    
    # Aid Programs with claims
    programs_with_claims = claims_qs.values('assistance__program__id', 'assistance__program__name').distinct().count()
    
    # Barangays Covered
    barangays_covered = claims_qs.values('family__household__barangay').distinct().count()
    total_barangays = Barangay.objects.count()
    
    # --- Claims by Aid Type ---
    aid_type_data = (
        claims_qs.values('assistance__aid_category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    claims_by_aid_type = [
        {
            'name': item['assistance__aid_category__name'],
            'count': item['count'],
            'percentage': round((item['count'] / total_claims) * 100, 1) if total_claims > 0 else 0
        }
        for item in aid_type_data
    ]
    
    # --- Claims Trend Over Time (Monthly) ---
    from collections import defaultdict
    from django.utils.dateformat import DateFormat
    trend_data = defaultdict(int)
    for claim in claims_qs:
        month_key = DateFormat(claim.claimed_at).format('Y-m')
        trend_data[month_key] += 1
    
    # Sort and format trend data
    sorted_months = sorted(trend_data.keys())
    claims_trend = [
        {
            'month': month,
            'count': trend_data[month]
        }
        for month in sorted_months
    ]
    
    # --- Beneficiaries by Age Bracket ---
    age_bracket_counts = [0] * len(AGE_BRACKETS)
    for claim in claims_qs:
        if claim.family_member and claim.family_member.age is not None:
            bracket_idx = get_age_bracket_index(claim.family_member.age)
            if bracket_idx is not None:
                # Count unique beneficiaries per bracket
                if claim.family_member_id:
                    key = f"member_{claim.family_member_id}"
                else:
                    key = f"family_{claim.family_id}"
                # We need to track unique per bracket
                # For simplicity, count all claims (could be refined to unique per bracket)
                age_bracket_counts[bracket_idx] += 1
    
    beneficiaries_by_age = [
        {
            'label': bracket['label'],
            'count': age_bracket_counts[i]
        }
        for i, bracket in enumerate(AGE_BRACKETS)
    ]
    
    # --- Beneficiaries by Gender ---
    gender_counts = defaultdict(int)
    for claim in claims_qs:
        if claim.family_member and claim.family_member.sex:
            gender_counts[claim.family_member.sex] += 1
    
    beneficiaries_by_gender = [
        {'label': 'Male', 'count': gender_counts.get('M', 0)},
        {'label': 'Female', 'count': gender_counts.get('F', 0)}
    ]
    
    # --- Top 5 Barangays by Claims ---
    barangay_data = (
        claims_qs.values('family__household__barangay__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    top_barangays = [
        {
            'name': item['family__household__barangay__name'] or 'Unknown',
            'count': item['count']
        }
        for item in barangay_data
    ]
    
    # --- Recent Aid Claims ---
    recent_claims = claims_qs.order_by('-claimed_at')[:20]
    recent_claims_data = []
    for claim in recent_claims:
        beneficiary_name = (
            f"{claim.family_member.first_name} {claim.family_member.last_name}"
            if claim.family_member
            else f"{claim.family.family_name} Family"
        )
        recent_claims_data.append({
            'id': claim.id,
            'beneficiary': beneficiary_name,
            'aid_type': f"{claim.assistance.program.name} › {claim.assistance.aid_category.name}",
            'barangay': claim.family.household.barangay.name if claim.family.household.barangay else 'N/A',
            'claimed_at': claim.claimed_at.strftime('%Y-%m-%d %H:%M'),
            'amount': float(claim.amount) if claim.amount else None,
            'claim_type': claim.claim_type
        })
    
    # --- Summary by Aid Program ---
    program_data = (
        claims_qs.values('assistance__program__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    summary_by_program = [
        {
            'program': item['assistance__program__name'],
            'count': item['count'],
            'percentage': round((item['count'] / total_claims) * 100, 1) if total_claims > 0 else 0
        }
        for item in program_data
    ]
    
    # --- Filter Options ---
    aid_categories = AidCategory.objects.filter(is_active=True).values('id', 'name')
    programs = Program.objects.filter(is_active=True).values('id', 'name')
    barangays = Barangay.objects.all().values('id', 'name')
    
    return JsonResponse({
        'kpis': {
            'total_claims': total_claims,
            'unique_beneficiaries': unique_beneficiaries,
            'total_aid_released': float(total_aid_released),
            'walkin_count': walkin_count,
            'programs_with_claims': programs_with_claims,
            'barangays_covered': barangays_covered,
            'total_barangays': total_barangays,
        },
        'claims_by_aid_type': claims_by_aid_type,
        'claims_trend': claims_trend,
        'beneficiaries_by_age': beneficiaries_by_age,
        'beneficiaries_by_gender': beneficiaries_by_gender,
        'top_barangays': top_barangays,
        'recent_claims': recent_claims_data,
        'summary_by_program': summary_by_program,
        'filter_options': {
            'aid_categories': list(aid_categories),
            'programs': list(programs),
            'barangays': list(barangays),
            'age_brackets': AGE_BRACKETS,
        }
    })


@login_required
@session_protected
def barangay_analytics(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay = request.user.barangay

    labels, data, total_count = get_category_claims_data(barangay=barangay)

    total_families = Family.objects.filter(
        household__barangay=barangay,
        is_active=True
    ).count()

    claimed_families = AidClaim.objects.filter(
        family__household__barangay=barangay
    ).values('family').distinct().count()

    # Demographics data (reused from barangay_dashboard pattern)
    pwd_count = FamilyMember.objects.filter(family__household__barangay=barangay, is_pwd=True).count()
    solo_parent_count = FamilyMember.objects.filter(family__household__barangay=barangay, is_solo_parent=True).count()
    senior_count = FamilyMember.objects.filter(family__household__barangay=barangay, is_senior_citizen=True).count()
    
    total_families_rfid = Family.objects.filter(household__barangay=barangay, rfid_uid__isnull=False).exclude(rfid_uid="").count()
    rfid_completion_percent = round((total_families_rfid / total_families) * 100) if total_families > 0 else 0

    # Enhanced summary calculations
    unserved_families = total_families - claimed_families
    coverage_rate = round((claimed_families / total_families) * 100) if total_families > 0 else 0

    return render(request, 'monitoring/barangay_analytics.html', {
        'labels': labels,
        'data': data,
        'total_count': total_count,
        'barangay': barangay,
        'total_families': total_families,
        'claimed_families': claimed_families,
        'pwd_count': pwd_count,
        'solo_parent_count': solo_parent_count,
        'senior_count': senior_count,
        'total_families_rfid': total_families_rfid,
        'rfid_completion_percent': rfid_completion_percent,
        'unserved_families': unserved_families,
        'coverage_rate': coverage_rate,
    })


@login_required(login_url='login')
@session_protected
def barangay_schedule_status(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay_obj = request.user.barangay
    now = timezone.localtime(timezone.now())

    # Auto-deactivate logic removed

    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    ).select_related('assistance', 'assistance__program', 'assistance__aid_category', 'barangay')

    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_finished=False,
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
            'location': s.location,
            'location_lat': float(s.location_lat) if s.location_lat else None,
            'location_lng': float(s.location_lng) if s.location_lng else None,
            'barangay': str(s.barangay) if s.barangay else 'All Barangays',
        } for s in qs]

    return JsonResponse({
        'active': serialize(active_schedules),
        'upcoming': serialize(upcoming_schedules),
    })


