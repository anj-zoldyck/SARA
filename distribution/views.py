
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


@login_required
@session_protected
def scan_rfid(request):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF', 'BARANGAY'):
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
        error = "No active distribution schedule right now."
    elif not aid_schedule.assistance:
        error = "Active schedule has no assistance type configured. Please contact admin."

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json' or 'application/json' in request.content_type

    if error and is_ajax and request.method == 'POST':
        return JsonResponse({'status': 'error', 'message': error})

    # ----------------- Handle RFID SCAN -----------------
    if request.method == 'POST' and aid_schedule and aid_schedule.assistance:
        uid = request.POST.get('rfid_uid')
        member_id = request.POST.get('family_member')
        assistance = aid_schedule.assistance

        if not uid and not member_id and is_ajax:
            # Handle standard json body just in case
            try:
                data = json.loads(request.body)
                uid = data.get('rfid_uid')
                member_id = data.get('family_member')
            except:
                pass

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
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': error})
            return render(request, 'distribution/scan_rfid.html', {'error': error, 'aid_schedule': aid_schedule})

        # -------- FAMILY-BASED assistance --------
        if assistance.beneficiary_type == 'family':
            already_claimed = AidClaim.objects.filter(
                family=family,
                assistance=assistance,
                schedule=aid_schedule
            ).exists()

            if already_claimed:
                error = f"{family.family_name} has already claimed {assistance.aid_category.name} for this schedule."
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error})
            else:
                AidClaim.objects.create(
                    family=family,
                    assistance=assistance,
                    schedule=aid_schedule,
                    created_by=request.user,
                )
                success = f"{family.family_name} successfully claimed {assistance.aid_category.name}."
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': success,
                        'name': family.family_name,
                        'assistance_label': f"{assistance.program.name} › {assistance.aid_category.name}"
                    })

        # -------- INDIVIDUAL-BASED assistance --------
        elif assistance.beneficiary_type == 'individual':
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
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': error})
                else:
                    AidClaim.objects.create(
                        family=family,
                        family_member=member,
                        assistance=assistance,
                        schedule=aid_schedule,
                        created_by=request.user,
                    )
                    success = f"{member.first_name} {member.last_name} successfully claimed {assistance.aid_category.name}."
                    if is_ajax:
                        return JsonResponse({
                            'status': 'success',
                            'message': success,
                            'name': f"{member.first_name} {member.last_name}",
                            'profile_image': member.profile_image.url if member.profile_image else None,
                            'assistance_label': f"{assistance.program.name} › {assistance.aid_category.name}"
                        })
                    eligible_members = None

            else:
                # No member selected yet — return members list for AJAX modal
                all_members = family.members.all()
                claimed_member_ids = AidClaim.objects.filter(
                    family=family,
                    assistance=assistance,
                    schedule=aid_schedule,
                    family_member__isnull=False
                ).values_list('family_member_id', flat=True)

                member_data = []
                for m in all_members:
                    reasons = []
                    if assistance.minimum_age and (m.age is None or m.age < assistance.minimum_age):
                        reasons.append(f"Under {assistance.minimum_age}")
                    if assistance.requires_pwd and not m.is_pwd:
                        reasons.append("Not registered PWD")
                    if assistance.requires_solo_parent and not m.is_solo_parent:
                        reasons.append("Not registered Solo Parent")

                    if reasons:
                        status = 'ineligible'
                        reason_str = ", ".join(reasons)
                    elif m.id in claimed_member_ids:
                        status = 'eligible_claimed'
                        reason_str = "Already Claimed"
                    else:
                        status = 'eligible_unclaimed'
                        reason_str = "Eligible"

                    member_data.append({
                        'id': m.id,
                        'name': f"{m.first_name} {m.last_name}",
                        'status': status,
                        'reason': reason_str,
                        'profile_image': m.profile_image.url if m.profile_image else None
                    })

                if is_ajax:
                    has_eligible = any(m['status'] == 'eligible_unclaimed' for m in member_data)
                    if not has_eligible:
                        return JsonResponse({
                            'status': 'error', 
                            'message': f"All eligible members of this family have already claimed {assistance.aid_category.name} today."
                        })

                    criteria = []
                    if assistance.minimum_age: criteria.append(f"{assistance.minimum_age}+")
                    if assistance.requires_pwd: criteria.append("PWD")
                    if assistance.requires_solo_parent: criteria.append("Solo Parent")
                    criteria_str = " + ".join(criteria) if criteria else "No specific criteria"

                    return JsonResponse({
                        'status': 'needs_selection',
                        'family_name': family.family_name,
                        'address': family.household.address,
                        'criteria': f"{assistance.program.name} › {assistance.aid_category.name} — {criteria_str}",
                        'members': member_data
                    })
                else:
                    # fallback for non-ajax
                    eligible_members = all_members.exclude(id__in=claimed_member_ids)
                    if assistance.minimum_age:
                        today = date.today()
                        try:
                            threshold_date = today.replace(year=today.year - assistance.minimum_age)
                        except ValueError:
                            threshold_date = today.replace(year=today.year - assistance.minimum_age, day=28)
                        eligible_members = eligible_members.filter(birthdate__lte=threshold_date)
                    if assistance.requires_pwd:
                        eligible_members = eligible_members.filter(is_pwd=True)
                    if assistance.requires_solo_parent:
                        eligible_members = eligible_members.filter(is_solo_parent=True)
                        
                    if not eligible_members.exists():
                        error = f"All eligible members have already claimed {assistance.aid_category.name} for this schedule."
                    else:
                        return render(request, 'distribution/scan_rfid.html', {
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

    if request.user.role == 'MSWDO_STAFF':
        claims = claims.filter(created_by=request.user)

    recent_claims = claims.order_by('-claimed_at')[:20]
    barangays = Barangay.objects.all()

    return render(request, 'distribution/scan_rfid.html', {
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
        'hide_sidebar': True,
    })


