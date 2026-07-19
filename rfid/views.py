
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

User = get_user_model()


@login_required
@session_protected
@mswdo_or_staff_required
def register_rfid(request, family_id=None):

    # ── If a specific family was linked to, go straight to the
    #    registration form (your existing behaviour) ────────────
    if family_id:
        selected_family = get_object_or_404(Family, id=family_id)
        error = success = None

        if request.method == 'POST':
            rfid_uid = request.POST.get('rfid_uid')
            if not rfid_uid:
                error = "Please scan an RFID card."
            else:
                existing = Family.objects.filter(rfid_uid=rfid_uid).exclude(id=selected_family.id).first()
                if existing:
                    error = f"RFID already assigned to {existing.family_name}."
                else:
                    selected_family.rfid_uid = rfid_uid
                    selected_family.save()
                    success = f"RFID successfully registered to {selected_family.family_name}."

        return render(request, 'accounts/register_rfid_form.html', {
            'selected_family': selected_family,
            'error': error,
            'success': success,
            'requires_auth': True,
        })

    # ── Overview page (no family_id) ───────────────────────────
    # Read filter params
    selected_barangay_id = request.GET.get('barangay')
    selected_zone_id     = request.GET.get('zone')

    all_barangays = Barangay.objects.all().order_by('name')
    all_zones     = Zone.objects.select_related('barangay').all().order_by('barangay__name', 'name')

    selected_barangay = None
    selected_zone     = None

    if selected_barangay_id:
        selected_barangay = get_object_or_404(Barangay, id=selected_barangay_id)
    if selected_zone_id:
        selected_zone = get_object_or_404(Zone, id=selected_zone_id)

    # ── Build a queryset of families matching the filter ───────
    families_qs = Family.objects.select_related(
        'household__zone__barangay'
    )

    if selected_barangay:
        families_qs = families_qs.filter(
            household__zone__barangay=selected_barangay
        )
    if selected_zone:
        families_qs = families_qs.filter(
            household__zone=selected_zone
        )

    total        = families_qs.count()
    registered   = families_qs.filter(rfid_uid__isnull=False).exclude(rfid_uid='').count()
    unregistered = total - registered
    rate         = round((registered / total * 100), 1) if total else 0

    stats = {
        'total':        total,
        'registered':   registered,
        'unregistered': unregistered,
        'rate':         rate,
    }

    # ── Per-barangay summary (for table + bar chart) ───────────
    #    Always group by barangay within the current filter.
    barangay_summary = []
    bar_labels       = []
    bar_registered   = []
    bar_unregistered = []

    # Which barangays to show in the summary?
    if selected_barangay:
        summary_barangays = [selected_barangay]
    else:
        # If only a zone is selected, show only barangays that
        # have that zone — which may span multiple barangays.
        if selected_zone:
            summary_barangays = Barangay.objects.filter(
                zones=selected_zone
            ).distinct().order_by('name')
        else:
            summary_barangays = all_barangays

    for brgy in summary_barangays:
        brgy_qs = families_qs.filter(household__zone__barangay=brgy)
        b_total  = brgy_qs.count()
        b_reg    = brgy_qs.filter(rfid_uid__isnull=False).exclude(rfid_uid='').count()
        b_unreg  = b_total - b_reg
        b_rate   = round((b_reg / b_total * 100), 1) if b_total else 0

        barangay_summary.append({
            'barangay':    brgy,
            'zone_filter': selected_zone.name if selected_zone else None,
            'total':       b_total,
            'registered':  b_reg,
            'unregistered': b_unreg,
            'rate':        b_rate,
        })

        bar_labels.append(brgy.name)
        bar_registered.append(b_reg)
        bar_unregistered.append(b_unreg)

    # ── Barangay cards: annotate with rfid counts ──────────────
    # We re-use summary_barangays but attach the counts directly
    # to the object so the template can use barangay.rfid_registered.
    filtered_barangays = []
    for row in barangay_summary:
        brgy = row['barangay']
        brgy.rfid_total      = row['total']
        brgy.rfid_registered = row['registered']
        filtered_barangays.append(brgy)

    import json

    context = {
        'barangays':         all_barangays,       # for the filter dropdown
        'all_zones':         all_zones,            # for the zone dropdown
        'selected_barangay': selected_barangay,
        'selected_zone':     selected_zone,

        'stats':             stats,
        'barangay_summary':  barangay_summary,
        'filtered_barangays': filtered_barangays,

        # JSON-safe lists for Chart.js
        'bar_labels':        json.dumps(bar_labels),
        'bar_registered':    json.dumps(bar_registered),
        'bar_unregistered':  json.dumps(bar_unregistered),

        'requires_auth': True,
    }

    return render(request, 'rfid/register_rfid.html', context)


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


@login_required
@session_protected
def rfid_overview(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")
    total_rfid = Household.objects.count()
    claimed = AidClaim.objects.filter(claimed_at__isnull=False).count()
    unclaimed = total_rfid - claimed
    return render(request, 'rfid/rfid_overview.html', {
        'rfid_claimed': claimed,
        'rfid_unclaimed': unclaimed
    })


