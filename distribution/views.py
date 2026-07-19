
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
from distribution.models import AidSchedule, AidClaim, GeneratedBeneficiaryList, GeneratedBeneficiary

from accounts.forms import UserEditForm, CreateUserForm
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm
from programs.forms import ProgramForm, AidCategoryForm, AssistanceForm
from programs.eligibility import check_eligibility, get_eligibility_badges
# from distribution.forms import AidScheduleForm  # if any

from django.utils.safestring import mark_safe
from distribution.services import get_active_aid_schedule, get_active_schedule, is_staff_assigned_to_scan
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from django.urls import reverse
from django.core.cache import cache
import json

User = get_user_model()


@login_required
@session_protected
def schedule_distribution(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        assistance_id = request.POST.get('assistance')
        assistance = Assistance.objects.filter(id=assistance_id).first()

        if not assistance:
            messages.error(request, "Please select a valid assistance type.")
            return redirect('schedule_distribution')

        start = parse_datetime(request.POST.get('schedule_datetime'))

        if not start:
            messages.error(request, "Invalid date/time format. Please try again.")
            return redirect('schedule_distribution')

        if timezone.is_naive(start):
            start = timezone.make_aware(start)

        location = request.POST.get('location')
        barangay_id = request.POST.get('barangay')
        barangay = Barangay.objects.filter(id=barangay_id).first() if barangay_id else None
        
        enable_selection = request.POST.get('enable_selection') == 'on'
        
        from decimal import Decimal, InvalidOperation
        
        budget_raw = request.POST.get('budget', '').strip()
        per_beneficiary_raw = request.POST.get('per_beneficiary_amount', '').strip()

        budget = Decimal('0')
        per_beneficiary_amount = Decimal('0')
        
        if enable_selection:
            try:
                budget = Decimal(budget_raw) if budget_raw else Decimal('0')
                per_beneficiary_amount = Decimal(per_beneficiary_raw) if per_beneficiary_raw else Decimal('0')
            except InvalidOperation:
                # Handle invalid/non-numeric input gracefully — show a form error,
                # do not let a bad input crash the whole request
                # We use Decimal consistent with the rest of this codebase's handling of money values, avoiding floating-point precision issues.
                messages.error(request, "Invalid numeric input for budget or per-beneficiary amount.")
                return redirect('schedule_distribution')

        # Auto-expire logic removed as completion is now state-based (is_finished)

        schedule = AidSchedule.objects.create(
            assistance=assistance,
            schedule_datetime=start,
            location=location,
            barangay=barangay,
            budget=budget if enable_selection else Decimal('0'),
            per_beneficiary_amount=per_beneficiary_amount if enable_selection else Decimal('0')
        )

        if enable_selection and schedule.budget > Decimal('0') and schedule.per_beneficiary_amount > Decimal('0'):
            messages.success(request, f"Schedule created — generating your beneficiary list now...")
            return redirect('generate_beneficiaries', schedule_id=schedule.id)
        else:
            messages.success(request, f"Distribution scheduled successfully: {assistance}")
            return redirect('schedule_distribution')

    # GET
    assistances = Assistance.objects.select_related(
        'program', 'aid_category'
    ).filter(is_active=True).order_by('program__name', 'aid_category__name')
    barangays = Barangay.objects.all()

    return render(request, 'distribution/schedule_distribution.html', {
        'assistances': assistances,
        'barangays': barangays
    })


@login_required
@session_protected
def scan_rfid(request, schedule_id):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF', 'BARANGAY'):
        messages.error(request, "Access Denied.")
        return redirect('login')

    error = None
    success = None
    family = None
    family_members = None

    aid_schedule = get_object_or_404(AidSchedule.objects.select_related(
        'assistance',
        'assistance__program',
        'assistance__aid_category'
    ), id=schedule_id)

    if not aid_schedule.is_active or aid_schedule.is_finished:
        error = "This schedule is no longer active or has finished."
    elif not aid_schedule.assistance:
        error = "This schedule has no assistance type configured. Please contact admin."
        
    # -------- STAFF ASSIGNMENT ENFORCEMENT --------
    # This acts as a hard block against direct URL access.
    # If the user is unassigned to this schedule, they cannot access the kiosk view at all.
    if not is_staff_assigned_to_scan(request.user, aid_schedule):
        messages.error(request, "Access Denied — You are not assigned to process claims for this distribution.")
        if request.user.role == 'MSWDO':
            return redirect('mswdo_dashboard')
        elif request.user.role == 'MSWDO_STAFF':
            return redirect('staff_dashboard')
        else:
            return redirect('barangay_dashboard')

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

        # -------- Phase B: Beneficiary List Check --------
        # If the schedule has a generated beneficiary list, restrict processing to only those on the list.
        if hasattr(aid_schedule, 'beneficiary_list'):
            ben_list = aid_schedule.beneficiary_list
            is_listed = False
            
            if assistance.beneficiary_type == 'family':
                is_listed = ben_list.entries.filter(family=family).exists()
            else:
                is_listed = ben_list.entries.filter(household=family.household).exists()
                
            if not is_listed:
                error = "This household is not on the approved beneficiary list for this distribution."
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error})
                return render(request, 'distribution/scan_rfid.html', {'error': error, 'aid_schedule': aid_schedule})

        # -------- Phase B.1: Staff Assignment Check --------
        # Check if the staff member is assigned to process claims for this schedule/location.
        # This is independent of the beneficiary list check. Both can coexist.
        if not is_staff_assigned_to_scan(request.user, aid_schedule, family.household):
            error = "You are not assigned to process claims for this location."
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
                    claim_type='DISTRIBUTION',
                )
                success = f"{family.family_name} successfully claimed {assistance.aid_category.name}."
                
                # Completion Check
                distribution_just_finished = False
                if hasattr(aid_schedule, 'beneficiary_list'):
                    ben_list = aid_schedule.beneficiary_list
                    total_bens = ben_list.entries.filter(family__isnull=False).count()
                    claimed_families = AidClaim.objects.filter(schedule=aid_schedule).values('family').distinct().count()
                    if total_bens > 0 and claimed_families >= total_bens:
                        aid_schedule.is_finished = True
                        aid_schedule.finished_at = timezone.now()
                        aid_schedule.finish_reason = 'COMPLETED'
                        aid_schedule.save()
                        distribution_just_finished = True
                        
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': success,
                        'name': family.family_name,
                        'assistance_label': f"{assistance.program.name} › {assistance.aid_category.name}",
                        'distribution_just_finished': distribution_just_finished
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
                        claim_type='DISTRIBUTION',
                    )
                    success = f"{member.first_name} {member.last_name} successfully claimed {assistance.aid_category.name}."
                    
                    # Completion Check
                    distribution_just_finished = False
                    if hasattr(aid_schedule, 'beneficiary_list'):
                        ben_list = aid_schedule.beneficiary_list
                        is_finished = True
                        claimed_member_ids = set(AidClaim.objects.filter(schedule=aid_schedule, family_member__isnull=False).values_list('family_member_id', flat=True))
                        for entry in ben_list.entries.select_related('household').all():
                            if not is_finished: break
                            if entry.household:
                                for fam in entry.household.families.all():
                                    for m in fam.members.all():
                                        is_el, _ = check_eligibility(m, assistance)
                                        if is_el and m.id not in claimed_member_ids:
                                            is_finished = False
                                            break
                                    if not is_finished: break
                        if is_finished and ben_list.entries.exists():
                            aid_schedule.is_finished = True
                            aid_schedule.finished_at = timezone.now()
                            aid_schedule.finish_reason = 'COMPLETED'
                            aid_schedule.save()
                            distribution_just_finished = True

                    if is_ajax:
                        return JsonResponse({
                            'status': 'success',
                            'message': success,
                            'name': f"{member.first_name} {member.last_name}",
                            'profile_image': member.profile_image.url if member.profile_image else None,
                            'assistance_label': f"{assistance.program.name} › {assistance.aid_category.name}",
                            'distribution_just_finished': distribution_just_finished
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
                    is_eligible, reasons = check_eligibility(m, assistance)

                    if not is_eligible:
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

                    badges = get_eligibility_badges(assistance)
                    criteria = [b['label'] for b in badges]
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
                    unclaimed_members = all_members.exclude(id__in=claimed_member_ids)
                    eligible_members = []
                    for m in unclaimed_members:
                        is_el, _ = check_eligibility(m, assistance)
                        if is_el:
                            eligible_members.append(m)
                        
                    if not eligible_members:
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

@login_required(login_url='login')
@session_protected
def staff_walkin(request):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Access Denied")

    query = request.GET.get('q', '').strip()
    barangay_id = request.GET.get('barangay')
    zone_id = request.GET.get('zone')

    members = FamilyMember.objects.none()
    
    if query or barangay_id or zone_id:
        members = FamilyMember.objects.filter(family__is_active=True).select_related(
            'family', 'family__household', 'family__household__zone', 'family__household__barangay'
        )
        
        if query:
            # Split query into words and require ALL words to match somewhere across name fields
            # This correctly handles "Juan", "Dela Cruz", "Juan Dela Cruz", and "Dela Cruz Juan"
            words = query.split()
            q_objects = Q()
            for word in words:
                q_objects &= (
                    Q(first_name__icontains=word) |
                    Q(middle_name__icontains=word) |
                    Q(last_name__icontains=word)
                )
            members = members.filter(q_objects)
        
        if barangay_id:
            members = members.filter(family__household__barangay_id=barangay_id)
            
        if zone_id:
            members = members.filter(family__household__zone_id=zone_id)
            
        members = members.order_by('last_name', 'first_name')[:50]
        
    barangays = Barangay.objects.all().order_by('name')
    all_zones = Zone.objects.select_related('barangay').order_by('name')
    assistances = Assistance.objects.filter(is_active=True).select_related('program', 'aid_category')
    
    return render(request, 'distribution/staff_walkin.html', {
        'members': members,
        'barangays': barangays,
        'all_zones': all_zones,
        'assistances': assistances,
        'query': query,
        'selected_barangay': barangay_id,
        'selected_zone': zone_id,
    })

@login_required(login_url='login')
@session_protected
def staff_walkin_rfid_lookup(request):
    if request.user.role != 'MSWDO_STAFF':
        return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)
        
    uid = request.GET.get('rfid_uid', '').strip()
    if not uid:
        return JsonResponse({'status': 'error', 'message': 'No RFID provided.'})
        
    try:
        family = Family.objects.get(rfid_uid=uid, is_active=True)
    except Family.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No resident registered with this RFID card'})
        
    members = family.members.all().order_by('first_name')
    member_data = []
    for m in members:
        member_data.append({
            'id': m.id,
            'name': f"{m.first_name} {m.last_name}",
            'profile_image': m.profile_image.url if m.profile_image else None
        })
        
    return JsonResponse({
        'status': 'success',
        'family_name': family.family_name,
        'address': family.household.address,
        'barangay': family.household.barangay.name if family.household.barangay else '',
        'zone': family.household.zone.name if family.household.zone else '',
        'members': member_data
    })

@login_required(login_url='login')
@session_protected
def staff_walkin_claim(request):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Access Denied")
        
    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        assistance_id = request.POST.get('assistance_id')
        
        member = get_object_or_404(FamilyMember, id=member_id)
        assistance = get_object_or_404(Assistance, id=assistance_id, is_active=True)
        

        today = timezone.now().date()
        existing = AidClaim.objects.filter(
            family_member=member,
            assistance=assistance,
            claimed_at__date=today
        ).exists()
        
        if existing:
            return JsonResponse({
                'status': 'error',
                'message': 'This resident has already received this assistance today.'
            }, status=400)
            
        AidClaim.objects.create(
            family=member.family,
            family_member=member,
            assistance=assistance,
            schedule=None,
            claim_type='WALK_IN',
            created_by=request.user,
        )
        return JsonResponse({'status': 'success', 'message': f'Walk-in claim recorded for {member.first_name} {member.last_name}.'})
        
    return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)


@login_required
@session_protected
@mswdo_or_staff_required
def beneficiary_selection_landing(request):
    """
    Landing page for Beneficiary Selection and Staff Assignment. Lists active schedules.
    """
    schedules = AidSchedule.objects.filter(
        is_active=True
    ).select_related('assistance', 'assistance__program', 'assistance__aid_category').order_by('-schedule_datetime')
    
    return render(request, 'distribution/beneficiary_selection_landing.html', {
        'schedules': schedules,
    })

@login_required
@session_protected
def staff_walkin_member_modal(request, member_id):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden('Access Denied')
        
    member = get_object_or_404(
        FamilyMember.objects.select_related('family', 'family__household', 'family__household__zone', 'family__household__barangay'),
        id=member_id
    )
    
    claims = AidClaim.objects.filter(
        Q(family_member=member) | Q(family=member.family, family_member__isnull=True)
    ).select_related('assistance__program', 'assistance__aid_category').order_by('-claimed_at')[:5]
    
    assistances = Assistance.objects.filter(is_active=True).select_related('program', 'aid_category')
    
    return render(request, 'households/partials/walkin_profile_modal.html', {
        'member': member,
        'claims': claims,
        'assistances': assistances
    })

@login_required
@session_protected
def generate_beneficiaries(request, schedule_id):
    """
    Generates a beneficiary list for a specific schedule based on its budget and
    assistance rules. Saves the results to GeneratedBeneficiaryList.
    """
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    
    if hasattr(schedule, 'beneficiary_list'):
        messages.error(request, "A beneficiary list has already been generated for this schedule.")
        return redirect('mswdo_dashboard') # or some schedule detail page
        
    if not schedule.budget or not schedule.per_beneficiary_amount or schedule.per_beneficiary_amount <= 0:
        messages.error(request, "Budget and per-beneficiary amount must be set to generate a list.")
        return redirect('mswdo_dashboard')
        
    from programs.beneficiary_engine import calculate_slot_count, get_eligible_pool, rank_eligible_pool
    from distribution.models import GeneratedBeneficiaryList, GeneratedBeneficiary
    
    slot_count = calculate_slot_count(schedule.budget, schedule.per_beneficiary_amount)
    
    # Run the engine
    pool = get_eligible_pool(schedule.assistance, schedule.barangay, current_schedule=schedule)
    ranked_pool = rank_eligible_pool(pool, schedule.assistance.prioritization_strategy)
    # Take top N
    selected_beneficiaries = ranked_pool[:slot_count]
    
    # Create the persistent list
    ben_list = GeneratedBeneficiaryList.objects.create(
        schedule=schedule,
        generated_by=request.user,
        prioritization_strategy_used=schedule.assistance.prioritization_strategy
    )
    
    # Create individual entries
    entries = []
    is_family = schedule.assistance.beneficiary_type == 'family'
    for ben in selected_beneficiaries:
        if is_family:
            entries.append(GeneratedBeneficiary(beneficiary_list=ben_list, family=ben))
        else:
            entries.append(GeneratedBeneficiary(beneficiary_list=ben_list, household=ben))
            
    GeneratedBeneficiary.objects.bulk_create(entries)
    
    messages.success(request, f"Generated {len(selected_beneficiaries)} beneficiaries for this schedule.")
    return redirect('review_beneficiaries', schedule_id=schedule.id)

@login_required
@session_protected
def review_beneficiaries(request, schedule_id):
    """
    Displays the generated beneficiary list for review.
    """
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    
    if not hasattr(schedule, 'beneficiary_list'):
        messages.error(request, "No beneficiary list generated for this schedule yet.")
        return redirect('mswdo_dashboard')
        
    ben_list = schedule.beneficiary_list
    entries = ben_list.entries.select_related('family', 'household', 'family__household__barangay', 'household__barangay')
    
    from programs.beneficiary_engine import calculate_slot_count, get_eligible_pool
    slot_count = calculate_slot_count(schedule.budget, schedule.per_beneficiary_amount)
    
    # Get available candidates for manual override
    pool = get_eligible_pool(schedule.assistance, schedule.barangay, current_schedule=schedule)
    available_candidates = []
    
    is_family = schedule.assistance.beneficiary_type == 'family'
    if is_family:
        existing_ids = entries.values_list('family_id', flat=True)
        available_candidates = [ben for ben in pool if ben.id not in existing_ids]
    else:
        existing_ids = entries.values_list('household_id', flat=True)
        available_candidates = [ben for ben in pool if ben.id not in existing_ids]

    return render(request, 'distribution/review_beneficiaries.html', {
        'schedule': schedule,
        'ben_list': ben_list,
        'entries': entries,
        'slot_count': slot_count,
        'total_generated': entries.count(),
        'budget': schedule.budget,
        'per_amount': schedule.per_beneficiary_amount,
        'available_candidates': available_candidates,
        'is_family': is_family,
    })

@login_required
@session_protected
def manual_override_beneficiary(request, schedule_id):
    """
    Allows MSWDO admin to remove a generated entry and replace it with a new one.
    """
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    if not hasattr(schedule, 'beneficiary_list'):
        messages.error(request, "No beneficiary list exists for this schedule.")
        return redirect('review_beneficiaries', schedule_id=schedule.id)
        
    ben_list = schedule.beneficiary_list
    from distribution.models import GeneratedBeneficiary
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            is_family = schedule.assistance.beneficiary_type == 'family'
            
            # Read an array of IDs from the POST request (can handle one or many)
            added_count = 0
            
            if is_family:
                family_ids = request.POST.getlist('family_ids[]')
                if not family_ids:
                    # fallback to singular for robustness
                    single_id = request.POST.get('family_id')
                    if single_id: family_ids = [single_id]
                
                if family_ids:
                    entries_to_create = []
                    for fid in family_ids:
                        if not ben_list.entries.filter(family_id=fid).exists():
                            entries_to_create.append(GeneratedBeneficiary(
                                beneficiary_list=ben_list,
                                family_id=fid,
                                added_manually=True,
                                added_by=request.user
                            ))
                            added_count += 1
                    
                    if entries_to_create:
                        GeneratedBeneficiary.objects.bulk_create(entries_to_create)
                        
            else:
                household_ids = request.POST.getlist('household_ids[]')
                if not household_ids:
                    # fallback to singular for robustness
                    single_id = request.POST.get('household_id')
                    if single_id: household_ids = [single_id]
                    
                if household_ids:
                    entries_to_create = []
                    for hid in household_ids:
                        if not ben_list.entries.filter(household_id=hid).exists():
                            entries_to_create.append(GeneratedBeneficiary(
                                beneficiary_list=ben_list,
                                household_id=hid,
                                added_manually=True,
                                added_by=request.user
                            ))
                            added_count += 1
                    
                    if entries_to_create:
                        GeneratedBeneficiary.objects.bulk_create(entries_to_create)
            
            if added_count > 0:
                messages.success(request, f"Successfully added {added_count} manual overrides.")
            else:
                messages.warning(request, "No valid or new overrides were added.")
                
        elif action == 'remove':
            entry_id = request.POST.get('entry_id')
            entry = get_object_or_404(GeneratedBeneficiary, id=entry_id, beneficiary_list=ben_list)
            entry.delete()
            messages.success(request, "Beneficiary removed from the list.")
            
        return redirect('review_beneficiaries', schedule_id=schedule.id)
            
    return redirect('review_beneficiaries', schedule_id=schedule.id)


@login_required
@session_protected
def search_eligible_candidates(request, schedule_id):
    """
    AJAX endpoint for searching eligible candidates to manually add to a beneficiary list.
    """
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    q = request.GET.get('q', '').strip().lower()
    
    if not hasattr(schedule, 'beneficiary_list'):
        return JsonResponse({'status': 'error', 'message': 'No list generated yet.'}, status=400)
        
    ben_list = schedule.beneficiary_list
    entries = ben_list.entries.all()
    
    from programs.beneficiary_engine import get_eligible_pool
    pool = get_eligible_pool(schedule.assistance, schedule.barangay, current_schedule=schedule)
    
    is_family = schedule.assistance.beneficiary_type == 'family'
    results = []
    
    if is_family:
        existing_ids = entries.values_list('family_id', flat=True)
        available = [ben for ben in pool if ben.id not in existing_ids]
        
        for cand in available:
            # Split query into words and require ALL words to match
            words = q.split() if q else []
            if not words:
                # No query - include all available candidates
                results.append({
                    'id': cand.id,
                    'name': f"{cand.family_name} Family",
                    'subtitle': cand.household.barangay.name if cand.household.barangay else "No Barangay",
                    'is_family': True
                })
            else:
                # Check if all words match in family name or barangay
                name_lower = cand.family_name.lower()
                barangay_name = cand.household.barangay.name.lower() if cand.household.barangay else ""
                all_words_match = all(
                    word in name_lower or word in barangay_name
                    for word in words
                )
                if all_words_match:
                    results.append({
                        'id': cand.id,
                        'name': f"{cand.family_name} Family",
                        'subtitle': cand.household.barangay.name if cand.household.barangay else "No Barangay",
                        'is_family': True
                    })
    else:
        existing_ids = entries.values_list('household_id', flat=True)
        available = [ben for ben in pool if ben.id not in existing_ids]
        
        for cand in available:
            first_family = cand.families.first()
            head_member = first_family.head_member if first_family else None
            if not head_member and first_family:
                head_member = first_family.members.first()
                
            head = f"{head_member.first_name} {head_member.last_name}" if head_member else "No Head"
            
            # Split query into words and require ALL words to match
            words = q.split() if q else []
            if not words:
                # No query - include all available candidates
                results.append({
                    'id': cand.id,
                    'name': head,
                    'subtitle': cand.barangay.name if cand.barangay else "No Barangay",
                    'is_family': False
                })
            else:
                # Check if all words match in head name or barangay
                head_lower = head.lower()
                barangay_name = cand.barangay.name.lower() if cand.barangay else ""
                all_words_match = all(
                    word in head_lower or word in barangay_name
                    for word in words
                )
                if all_words_match:
                    results.append({
                        'id': cand.id,
                        'name': head,
                        'subtitle': cand.barangay.name if cand.barangay else "No Barangay",
                        'is_family': False
                    })
                
    return JsonResponse({'status': 'success', 'results': results[:20]})


@login_required
@session_protected
def assign_staff(request, schedule_id):
    """
    Manage staff assignments for a specific schedule.
    Allows MSWDO Admin to assign MSWDO_STAFF to specific barangays/zones.
    """
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    from distribution.models import AssignedTo
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'assign':
            staff_id = request.POST.get('staff')
            zone_id = request.POST.get('zone')
            
            # Inherit barangay from schedule if set, else read from POST
            if schedule.barangay:
                barangay_id = schedule.barangay.id
            else:
                barangay_id = request.POST.get('barangay')
            
            if not staff_id or not barangay_id:
                messages.error(request, "Staff and Barangay are required.")
                return redirect('assign_staff', schedule_id=schedule.id)
                
            staff_user = get_object_or_404(User, id=staff_id, role='MSWDO_STAFF')
            barangay = get_object_or_404(Barangay, id=barangay_id)
            
            # Ensure the selected barangay matches the schedule's barangay if the schedule is scope-locked
            if schedule.barangay and barangay != schedule.barangay:
                messages.error(request, "This schedule is locked to a specific barangay.")
                return redirect('assign_staff', schedule_id=schedule.id)
                
            zone = None
            if zone_id:
                zone = get_object_or_404(Zone, id=zone_id, barangay=barangay)
                
            # Check for existing
            if AssignedTo.objects.filter(schedule=schedule, staff=staff_user, barangay=barangay, zone=zone).exists():
                messages.error(request, "This staff member is already assigned to this exact location.")
            else:
                AssignedTo.objects.create(
                    schedule=schedule,
                    staff=staff_user,
                    barangay=barangay,
                    zone=zone,
                    assigned_by=request.user
                )
                messages.success(request, f"Assigned {staff_user.first_name} {staff_user.last_name} successfully.")
                
        elif action == 'remove':
            assignment_id = request.POST.get('assignment_id')
            assignment = get_object_or_404(AssignedTo, id=assignment_id, schedule=schedule)
            assignment.delete()
            messages.success(request, "Staff assignment removed.")
            
        return redirect('assign_staff', schedule_id=schedule.id)
        
    # GET
    assignments = schedule.assignments.select_related('staff', 'barangay', 'zone').order_by('barangay__name', 'zone__name', 'staff__first_name')
    staff_list = User.objects.filter(role='MSWDO_STAFF', is_active=True).order_by('first_name')
    barangays = Barangay.objects.all().order_by('name')
    zones = Zone.objects.select_related('barangay').all() # Useful for cascading
    
    return render(request, 'distribution/assign_staff.html', {
        'schedule': schedule,
        'assignments': assignments,
        'staff_list': staff_list,
        'barangays': barangays,
        'zones': zones,
    })

@login_required
@session_protected
def finish_distribution(request, schedule_id):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
        
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    
    if request.method == 'POST':
        schedule.is_finished = True
        schedule.finished_at = timezone.now()
        schedule.finished_by = request.user
        schedule.finish_reason = 'FORCED'
        schedule.save()
        messages.success(request, "Distribution has been manually finished.")
        if request.user.role == 'MSWDO':
            return redirect('mswdo_dashboard')
        return redirect('staff_dashboard')
        
    return HttpResponseForbidden("Invalid Method")

@login_required
@session_protected
def generate_report_stub(request):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
    return render(request, 'distribution/generate_report_stub.html')

@login_required
@session_protected
def beneficiary_detail_modal(request, entry_id):
    """
    Returns the HTML for the beneficiary detail modal in the review beneficiaries table.
    """
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
        
    from distribution.models import GeneratedBeneficiary
    entry = get_object_or_404(
        GeneratedBeneficiary.objects.select_related(
            'family', 'family__household', 'family__household__zone', 'family__household__barangay',
            'household', 'household__zone', 'household__barangay'
        ),
        id=entry_id
    )
    
    return render(request, 'distribution/partials/beneficiary_detail_modal.html', {
        'entry': entry,
    })
