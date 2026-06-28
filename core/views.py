
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
        'expired_schedules': expired_schedules,
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

    # Auto-deactivate expired schedules
    AidSchedule.objects.filter(end_datetime__lt=now, is_active=True).update(is_active=False)

    # Active: started but not yet ended
    active_schedules = AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        end_datetime__gte=now,
        is_active=True
    ).filter(
        Q(barangay=barangay_obj) | Q(barangay__isnull=True)
    )

    # Upcoming: not yet started
    upcoming_schedules = AidSchedule.objects.filter(
        schedule_datetime__gt=now,
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

    # Auto-deactivate expired schedules
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

    context = {
        'household_count': household_count,
        'family_count': family_count,
        'today_claims': today_claims,
        'active_schedules': active_schedules,
        'upcoming_schedules': upcoming_schedules,
    }

    return render(request, 'core/staff_dashboard.html', context)


