
from urllib import request
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date, timedelta
from django.db.models import Count, Q
from django.core.paginator import Paginator

from accounts.decorators import session_protected
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
import calendar
from reports.analytics_utils import get_category_claims_data, get_unique_beneficiaries_count
from core.models import AuditLog

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
    
    # Leaderboard & per-barangay profiling progress
    barangays = Barangay.objects.annotate(
        household_count=Count('households', distinct=True),
        family_count=Count('households__families', distinct=True),
        rfid_count=Count('households__families', filter=Q(households__families__rfid_uid__isnull=False) & ~Q(households__families__rfid_uid=""), distinct=True)
    )
    barangay_count = barangays.count()


    household_count = Household.objects.count()  # Total households
    family_count = Family.objects.count()        # Total families

    # Demographics
    pwd_count = FamilyMember.objects.filter(is_pwd=True).count()
    solo_parent_count = FamilyMember.objects.filter(is_solo_parent=True).count()
    senior_count = FamilyMember.objects.filter(is_senior_citizen=True).count()

    # RFID Registration Rate
    total_families_rfid = Family.objects.filter(rfid_uid__isnull=False).exclude(rfid_uid="").count()
    rfid_completion_percent = round((total_families_rfid / family_count) * 100) if family_count > 0 else 0

    # User Accounts Activity
    pending_invitations = User.objects.filter(is_active=False).count()

    # Today's claim activity
    now_local = timezone.localtime(timezone.now())
    today_claims = AidClaim.objects.filter(claimed_at__date=now_local.date()).count()

    # NEW: pass active assistance options for the schedule form
    assistances = Assistance.objects.select_related(
        'program', 'aid_category'
    ).filter(is_active=True).order_by('program__name', 'aid_category__name')

    now = timezone.localtime(timezone.now())

    start_date = now.replace(day=1).date()
    last_day = calendar.monthrange(start_date.year, start_date.month)[1]
    end_date = now.replace(day=last_day).date()

    analytics_labels, analytics_data, _ = get_category_claims_data(
        start_date=start_date, end_date=end_date
    )
    this_month_beneficiaries = get_unique_beneficiaries_count(
        start_date=start_date, end_date=end_date
    )

    # Monthly trend data (last 6 months)
    monthly_trend_labels = []
    monthly_trend_data = []
    for i in range(5, -1, -1):
        month_date = now.replace(day=1) - timedelta(days=32 * i)
        month_date = month_date.replace(day=1)
        month_end = month_date.replace(day=calendar.monthrange(month_date.year, month_date.month)[1])
        month_name = month_date.strftime('%b %Y')
        monthly_trend_labels.append(month_name)
        month_claims = AidClaim.objects.filter(
            claimed_at__date__gte=month_date.date(),
            claimed_at__date__lte=month_end.date()
        ).count()
        monthly_trend_data.append(month_claims)

    # ACTIVE (ongoing)
    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    )

    # UPCOMING
    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_finished=False,
        is_active=True
    )

    # FINISHED
    finished_schedules = AidSchedule.objects.filter(
        is_finished=True
    )

    # Active Aid Schedules count (active + upcoming)
    active_aid_schedules_count = (active_schedules.count() + upcoming_schedules.count())

    context = {
        'barangays': barangays,
        'barangay_accounts': barangay_accounts,  # For table
        'barangay_count': barangay_count,
        
        'pwd_count': pwd_count,
        'solo_parent_count': solo_parent_count,
        'senior_count': senior_count,
        
        'rfid_completion_percent': rfid_completion_percent,
        'total_families_rfid': total_families_rfid,
        'family_count': family_count,
        
        'pending_invitations': pending_invitations,
        'today_claims': today_claims,

        'assistances': assistances,
        'barangayAcc_count': barangayAcc_count,

        'active_schedules': active_schedules,
        'upcoming_schedules': upcoming_schedules,
        'finished_schedules': finished_schedules,
        'assigned_schedule_ids': [], # MSWDO is not assigned to specific locations
        
        'analytics_labels': analytics_labels,
        'analytics_data': analytics_data,
        'this_month_beneficiaries': this_month_beneficiaries,
        'active_aid_schedules_count': active_aid_schedules_count,
        'demo_chart_labels': ['PWDs', 'Solo Parents', 'Senior Citizens'],
        'demo_chart_data': [pwd_count, solo_parent_count, senior_count],
        'monthly_trend_labels': monthly_trend_labels,
        'monthly_trend_data': monthly_trend_data,
    }

    return render(request, 'core/mswdo_dashboard.html', context)


@login_required(login_url='login')
@session_protected
def barangay_dashboard(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay_obj = request.user.barangay  # ForeignKey object or name — adjust below
    zones = Zone.objects.filter(barangay=barangay_obj)

    now = timezone.localtime(timezone.now())

    # Active: started but not yet finished
    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    )

    # Upcoming: not yet started
    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_finished=False,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    )

    # Local Demographics & Stats
    pwd_count = FamilyMember.objects.filter(family__household__barangay=barangay_obj, is_pwd=True).count()
    solo_parent_count = FamilyMember.objects.filter(family__household__barangay=barangay_obj, is_solo_parent=True).count()
    senior_count = FamilyMember.objects.filter(family__household__barangay=barangay_obj, is_senior_citizen=True).count()
    
    total_families = Family.objects.filter(household__barangay=barangay_obj).count()
    total_families_rfid = Family.objects.filter(household__barangay=barangay_obj, rfid_uid__isnull=False).exclude(rfid_uid="").count()
    rfid_completion_percent = round((total_families_rfid / total_families) * 100) if total_families > 0 else 0

    analytics_labels, analytics_data, total_claims = get_category_claims_data(barangay=barangay_obj)

    claimed_families = AidClaim.objects.filter(
        family__household__barangay=barangay_obj
    ).values('family').distinct().count()

    return render(request, 'core/barangay_dashboard.html', {
        'barangay': barangay_obj,
        'zones': zones,
        'active_schedules': active_schedules,
        'upcoming_schedules': upcoming_schedules,
        'pwd_count': pwd_count,
        'solo_parent_count': solo_parent_count,
        'senior_count': senior_count,
        'total_families': total_families,
        'total_families_rfid': total_families_rfid,
        'rfid_completion_percent': rfid_completion_percent,
        'analytics_labels': analytics_labels,
        'analytics_data': analytics_data,
        'total_claims': total_claims,
        'claimed_families': claimed_families,
    })

@login_required(login_url='login')
@session_protected
def staff_dashboard(request):
    # Only MSWDO_STAFF can access
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Access Denied")

    household_count = Household.objects.count()
    family_count = Family.objects.count()

    now = timezone.localtime(timezone.now())
    today_claims = AidClaim.objects.filter(claimed_at__date=now.date()).count()

    # ACTIVE (ongoing)
    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    )

    # UPCOMING
    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
        is_finished=False,
        is_active=True
    )

    context = {
        'household_count': household_count,
        'family_count': family_count,
        'today_claims': today_claims,
        'active_schedules': active_schedules,
        'upcoming_schedules': upcoming_schedules,
        'assigned_schedule_ids': list(request.user.distribution_assignments.values_list('schedule_id', flat=True)),
    }

    return render(request, 'core/staff_dashboard.html', context)


@login_required(login_url='login')
@session_protected
def audit_log_view(request):
    """
    MSWDO Admin-only view for reviewing system audit logs.
    Shows chronological list with filters for actor, action type, date range, and barangay.
    """
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    logs = AuditLog.objects.select_related('actor').all()

    # Filters
    actor_filter = request.GET.get('actor')
    action_type_filter = request.GET.get('action_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    barangay_filter = request.GET.get('barangay')

    if actor_filter:
        logs = logs.filter(actor_id=actor_filter)

    if action_type_filter:
        logs = logs.filter(action_type=action_type_filter)

    if date_from:
        try:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(date_from)
            if dt:
                logs = logs.filter(created_at__gte=dt)
        except:
            pass

    if date_to:
        try:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(date_to)
            if dt:
                logs = logs.filter(created_at__lte=dt)
        except:
            pass

    # Filter by barangay (via target model if applicable)
    if barangay_filter:
        # Filter logs where target is a schedule with that barangay
        from distribution.models import AidSchedule
        from django.contrib.contenttypes.models import ContentType
        schedule_ct = ContentType.objects.get_for_model(AidSchedule)
        logs = logs.filter(
            content_type=schedule_ct,
            object_id__in=AidSchedule.objects.filter(barangay_id=barangay_filter).values_list('id', flat=True)
        )

    logs = logs.order_by('-created_at')

    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Filter options
    users = User.objects.filter(role__in=['MSWDO', 'MSWDO_STAFF', 'BARANGAY']).order_by('username')
    action_types = AuditLog.ACTION_TYPE_CHOICES
    barangays = Barangay.objects.all().order_by('name')

    return render(request, 'core/audit_log.html', {
        'page_obj': page_obj,
        'users': users,
        'action_types': action_types,
        'barangays': barangays,
        'selected_actor': actor_filter,
        'selected_action_type': action_type_filter,
        'selected_date_from': date_from,
        'selected_date_to': date_to,
        'selected_barangay': barangay_filter,
    })


