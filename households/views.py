
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
from django.core.paginator import Paginator

from accounts.decorators import session_protected, mswdo_or_staff_required
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember, FloodProneArea, RELATIONSHIP_CHOICES, CIVIL_STATUS_CHOICES
from households.vulnerability import get_vulnerable_households, get_matched_demographic_flags
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AidClaim

from django.db import transaction
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm, SeniorCitizenProfileForm, SoloParentProfileForm, PWDProfileForm
from households.constants import OSM_TO_DB_BARANGAY_NAME
from households.excel_utils import RBIFormAImporter, RBIFormAExporter
from programs.forms import ProgramForm, AidCategoryForm, AssistanceForm
# from distribution.forms import AidScheduleForm  # if any

from django.utils.safestring import mark_safe
from distribution.services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from django.urls import reverse
from django.core.cache import cache
import json
import os
import tempfile
import time
import logging
from django.http import HttpResponse

User = get_user_model()

logger = logging.getLogger(__name__)


@login_required
@session_protected
@mswdo_or_staff_required
def barangay_list(request):

    barangays = Barangay.objects.all().order_by('name')

    return render(request, 'households/barangay_list.html', {
        'barangays': barangays,
    })


@login_required
@session_protected
@mswdo_or_staff_required
def residents_overview(request):
    # Get filter parameters
    selected_barangay_id = request.GET.get('barangay')
    selected_zone_id = request.GET.get('zone')
    search_query = request.GET.get('search', '').strip()
    filter_senior = request.GET.get('senior')
    filter_pwd = request.GET.get('pwd')
    filter_solo_parent = request.GET.get('solo_parent')

    all_barangays = Barangay.objects.all().order_by('name')
    all_zones = Zone.objects.select_related('barangay').all().order_by('barangay__name', 'name')

    selected_barangay = None
    selected_zone = None

    if selected_barangay_id:
        selected_barangay = get_object_or_404(Barangay, id=selected_barangay_id)
    if selected_zone_id:
        selected_zone = get_object_or_404(Zone, id=selected_zone_id)

    # Build queryset of family members
    members_qs = FamilyMember.objects.select_related(
        'family',
        'family__household',
        'family__household__zone',
        'family__household__zone__barangay'
    )

    # Apply barangay filter
    if selected_barangay:
        members_qs = members_qs.filter(family__household__zone__barangay=selected_barangay)

    # Apply zone filter
    if selected_zone:
        members_qs = members_qs.filter(family__household__zone=selected_zone)

    # Apply search filter (first name or last name)
    if search_query:
        members_qs = members_qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    # Apply category filters
    if filter_senior:
        members_qs = members_qs.filter(is_senior_citizen=True)
    if filter_pwd:
        members_qs = members_qs.filter(is_pwd=True)
    if filter_solo_parent:
        members_qs = members_qs.filter(is_solo_parent=True)

    # Order by last name, then first name
    members_qs = members_qs.order_by('last_name', 'first_name')

    # Calculate stats
    total_members = members_qs.count()
    total_families = members_qs.values('family').distinct().count()
    total_households = members_qs.values('family__household').distinct().count()
    seniors_count = members_qs.filter(is_senior_citizen=True).count()
    pwd_count = members_qs.filter(is_pwd=True).count()
    solo_parent_count = members_qs.filter(is_solo_parent=True).count()

    stats = {
        'total_members': total_members,
        'total_families': total_families,
        'total_households': total_households,
        'seniors_count': seniors_count,
        'pwd_count': pwd_count,
        'solo_parent_count': solo_parent_count,
    }

    # Pagination
    paginator = Paginator(members_qs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'barangays': all_barangays,
        'all_zones': all_zones,
        'selected_barangay': selected_barangay,
        'selected_zone': selected_zone,
        'search_query': search_query,
        'filter_senior': filter_senior,
        'filter_pwd': filter_pwd,
        'filter_solo_parent': filter_solo_parent,
        'members': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'requires_auth': True,
    }

    return render(request, 'households/residents_overview.html', context)


@login_required
@session_protected
@mswdo_or_staff_required
def barangay_zones(request, barangay_id):

    barangay = get_object_or_404(Barangay, id=barangay_id)
    zones = Zone.objects.filter(barangay=barangay).order_by('name')

    return render(request, 'households/barangay_zones.html', {
        'barangay': barangay,
        'zones': zones,
    })


@login_required
@session_protected
@mswdo_or_staff_required
def zone_households(request, zone_id):

    zone = get_object_or_404(
        Zone.objects.select_related('barangay'),
        id=zone_id
    )

    households = Household.objects.filter(
        zone=zone
    ).order_by('house_number')

    return render(request, 'households/zone_households.html', {
        'zone': zone,
        'barangay': zone.barangay,
        'households': households,
    })


@login_required
@session_protected
@mswdo_or_staff_required
def household_info(request, household_id):

    household = get_object_or_404(
        Household.objects.select_related('zone', 'barangay'),
        id=household_id
    )

    # Get all active families in the household
    families = Family.objects.filter(
        household=household,
        is_active=True
    ).order_by('family_name')

    return render(request, 'households/household_info.html', {
        'household': household,
        'families': families,
    })





@login_required(login_url='login')
@session_protected
def zone_detail(request, zone_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    households = Household.objects.filter(zone=zone)

    return render(request, 'households/zone_detail.html', {
        'zone': zone,
        'households': households
    })

@login_required(login_url='login')
@session_protected
def manage_flood_prone_areas(request, zone_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    
    return render(request, 'households/manage_flood_prone_areas.html', {
        'zone': zone,
        'barangay': zone.barangay,
    })

@login_required(login_url='login')
@session_protected
def manage_flood_prone_areas_api(request, zone_id):
    if request.user.role != 'BARANGAY':
        return JsonResponse({'error': 'Access Denied'}, status=403)

    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)

    if request.method == 'GET':
        areas = FloodProneArea.objects.filter(zone=zone)
        data = [{
            'id': a.id,
            'latitude': float(a.latitude),
            'longitude': float(a.longitude),
            'description': a.description
        } for a in areas]
        return JsonResponse({'areas': data})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            action = body.get('action')

            if action == 'add':
                lat = body.get('latitude')
                lng = body.get('longitude')
                desc = body.get('description', '')
                
                if lat is None or lng is None:
                    return JsonResponse({'error': 'Latitude and longitude are required.'}, status=400)
                
                area = FloodProneArea.objects.create(
                    zone=zone,
                    latitude=lat,
                    longitude=lng,
                    description=desc,
                    created_by=request.user
                )
                return JsonResponse({'success': True, 'id': area.id})
                
            elif action == 'delete':
                area_id = body.get('id')
                area = get_object_or_404(FloodProneArea, id=area_id, zone=zone)
                area.delete()
                return JsonResponse({'success': True})
                
            elif action == 'update':
                area_id = body.get('id')
                desc = body.get('description', '')
                area = get_object_or_404(FloodProneArea, id=area_id, zone=zone)
                area.description = desc
                area.save()
                return JsonResponse({'success': True})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)


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

    return render(request, 'households/add_household.html', {
        'form': form,
        'zone': zone
    })


@login_required(login_url='login')
@session_protected
def edit_household(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    household = get_object_or_404(
        Household,
        id=household_id,
        barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = HouseholdForm(request.POST, instance=household)
        if form.is_valid():
            form.save()
            return redirect('household_detail', household_id=household.id)
    else:
        form = HouseholdForm(instance=household)

    return render(request, 'households/edit_household.html', {
        'form': form,
        'household': household
    })


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

    return render(request, 'households/household_detail.html', {
        'household': household,
        'families': families
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

    return render(request, 'households/add_family.html', {
        'form': form,
        'household': household
    })


@login_required
@session_protected
def family_detail(request, family_id):
    # Allow Barangay Admin, MSWDO Admin, and MSWDO Staff
    if request.user.role not in ('BARANGAY', 'MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")

    # Scope the query differently per role
    if request.user.role == 'BARANGAY':
        # Barangay Admin can only see families in their own barangay
        family = get_object_or_404(
            Family.objects.select_related(
                'household', 'household__zone', 'household__barangay'
            ),
            id=family_id,
            household__barangay=request.user.barangay
        )
    else:
        # MSWDO Admin and MSWDO Staff have system-wide read access — no barangay restriction
        family = get_object_or_404(
            Family.objects.select_related(
                'household', 'household__zone', 'household__barangay'
            ),
            id=family_id
        )

    members = family.members.all().order_by('first_name', 'last_name')

    return render(request, 'households/family_detail.html', {
        'family': family,
        'members': members
    })


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
        form = FamilyMemberForm(request.POST, request.FILES)
        senior_form = SeniorCitizenProfileForm(request.POST, prefix='senior')
        solo_parent_form = SoloParentProfileForm(request.POST, prefix='solo')
        pwd_form = PWDProfileForm(request.POST, prefix='pwd')

        valid = form.is_valid()
        if valid:
            member_temp = form.save(commit=False)
            if member_temp.is_senior_citizen and not senior_form.is_valid():
                valid = False
            if member_temp.is_solo_parent and not solo_parent_form.is_valid():
                valid = False
            if member_temp.is_pwd and not pwd_form.is_valid():
                valid = False

        if valid:
            with transaction.atomic():
                member = form.save(commit=False)
                member.family = family
                member.save()
                
                if member.is_senior_citizen:
                    senior_profile = senior_form.save(commit=False)
                    senior_profile.member = member
                    senior_profile.registered_by = request.user
                    senior_profile.save()
                
                if member.is_solo_parent:
                    solo_profile = solo_parent_form.save(commit=False)
                    solo_profile.member = member
                    solo_profile.registered_by = request.user
                    solo_profile.save()

                if member.is_pwd:
                    pwd_profile = pwd_form.save(commit=False)
                    pwd_profile.member = member
                    pwd_profile.registered_by = request.user
                    pwd_profile.save()
                    
                return redirect('family_detail', family_id=family.id)
    else:
        form = FamilyMemberForm()
        senior_form = SeniorCitizenProfileForm(prefix='senior')
        solo_parent_form = SoloParentProfileForm(prefix='solo')
        pwd_form = PWDProfileForm(prefix='pwd')

    family_members = family.members.all()
    children_0_6 = []
    children_7_22 = []
    children_22_plus = []

    for fm in family_members:
        if fm.relationship in ['SON', 'DAUGHTER'] and fm.age is not None:
            if fm.age <= 6:
                children_0_6.append(fm)
            elif fm.age <= 22:
                children_7_22.append(fm)
            else:
                children_22_plus.append(fm)

    return render(request, 'households/add_member.html', {
        'form': form,
        'senior_form': senior_form,
        'solo_parent_form': solo_parent_form,
        'pwd_form': pwd_form,
        'family': family,
        'family_members': family_members,
        'children_0_6': children_0_6,
        'children_7_22': children_7_22,
        'children_22_plus': children_22_plus,
    })


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
    
    senior_instance = getattr(member, 'senior_profile', None)
    solo_instance = getattr(member, 'solo_parent_profile', None)
    pwd_instance = getattr(member, 'pwd_profile', None)

    if request.method == 'POST':
        form = FamilyMemberForm(request.POST, request.FILES, instance=member)
        senior_form = SeniorCitizenProfileForm(request.POST, prefix='senior', instance=senior_instance)
        solo_parent_form = SoloParentProfileForm(request.POST, prefix='solo', instance=solo_instance)
        pwd_form = PWDProfileForm(request.POST, prefix='pwd', instance=pwd_instance)

        valid = form.is_valid()
        if valid:
            member_temp = form.save(commit=False)
            if member_temp.is_senior_citizen and not senior_form.is_valid():
                valid = False
            if member_temp.is_solo_parent and not solo_parent_form.is_valid():
                valid = False
            if member_temp.is_pwd and not pwd_form.is_valid():
                valid = False

        if valid:
            with transaction.atomic():
                updated_member = form.save()

                if updated_member.is_senior_citizen:
                    senior_profile = senior_form.save(commit=False)
                    senior_profile.member = updated_member
                    if not senior_profile.registered_by_id:
                        senior_profile.registered_by = request.user
                    senior_profile.save()
                else:
                    if hasattr(updated_member, 'senior_profile'):
                        updated_member.senior_profile.delete()
                
                if updated_member.is_solo_parent:
                    solo_profile = solo_parent_form.save(commit=False)
                    solo_profile.member = updated_member
                    if not solo_profile.registered_by_id:
                        solo_profile.registered_by = request.user
                    solo_profile.save()
                else:
                    if hasattr(updated_member, 'solo_parent_profile'):
                        updated_member.solo_parent_profile.delete()

                if updated_member.is_pwd:
                    pwd_profile = pwd_form.save(commit=False)
                    pwd_profile.member = updated_member
                    if not pwd_profile.registered_by_id:
                        pwd_profile.registered_by = request.user
                    pwd_profile.save()
                else:
                    if hasattr(updated_member, 'pwd_profile'):
                        updated_member.pwd_profile.delete()

                return redirect('family_detail', family_id=updated_member.family.id)
    else:
        form = FamilyMemberForm(instance=member)
        senior_form = SeniorCitizenProfileForm(prefix='senior', instance=senior_instance)
        solo_parent_form = SoloParentProfileForm(prefix='solo', instance=solo_instance)
        pwd_form = PWDProfileForm(prefix='pwd', instance=pwd_instance)

    family_members = member.family.members.exclude(id=member.id)
    children_0_6 = []
    children_7_22 = []
    children_22_plus = []

    for fm in family_members:
        if fm.relationship in ['SON', 'DAUGHTER'] and fm.age is not None:
            if fm.age <= 6:
                children_0_6.append(fm)
            elif fm.age <= 22:
                children_7_22.append(fm)
            else:
                children_22_plus.append(fm)

    return render(request, 'households/edit_member.html', {
        'form': form,
        'senior_form': senior_form,
        'solo_parent_form': solo_parent_form,
        'pwd_form': pwd_form,
        'member': member,
        'family_members': family_members,
        'children_0_6': children_0_6,
        'children_7_22': children_7_22,
        'children_22_plus': children_22_plus,
    })




@login_required
@session_protected
def member_details_modal(request, member_id):
    if request.user.role not in ('BARANGAY', 'MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden('Access Denied')

    if request.user.role == 'BARANGAY':
        member = get_object_or_404(
            FamilyMember,
            id=member_id,
            family__household__barangay=request.user.barangay
        )
    else:
        # MSWDO Admin and MSWDO Staff have system-wide read access — no barangay restriction
        member = get_object_or_404(FamilyMember, id=member_id)

    claims = AidClaim.objects.filter(
        Q(family_member=member) | Q(family=member.family, family_member__isnull=True)
    ).select_related('assistance__program', 'assistance__aid_category').order_by('-claimed_at')

    return render(request, 'households/partials/member_detail_modal.html', {
        'member': member,
        'claims': claims
    })


@login_required
@session_protected
@mswdo_or_staff_required
def member_profile_view_modal(request, member_id):
    member = get_object_or_404(
        FamilyMember.objects.select_related(
            'family',
            'family__household',
            'family__household__zone',
            'family__household__zone__barangay'
        ),
        id=member_id
    )

    claims = AidClaim.objects.filter(
        Q(family_member=member) | Q(family=member.family, family_member__isnull=True)
    ).select_related('assistance__program', 'assistance__aid_category').order_by('-claimed_at')

    return render(request, 'households/partials/member_profile_view_modal.html', {
        'member': member,
        'claims': claims
    })

@login_required
@session_protected
def household_modal_content(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden('Access Denied')

    household = get_object_or_404(
        Household.objects.prefetch_related('families', 'families__members'),
        id=household_id,
        barangay=request.user.barangay
    )

    total_families = household.families.count()
    total_members = sum(f.members.count() for f in household.families.all())

    return render(request, 'households/partials/_household_modal_content.html', {
        'household': household,
        'total_families': total_families,
        'total_members': total_members,
    })

@login_required
@session_protected
def household_map(request):
    db_to_osm = {v: k for k, v in OSM_TO_DB_BARANGAY_NAME.items()}
    boundary_mode = 'municipal'
    assigned_barangay = None

    if request.user.role == 'BARANGAY':
        boundary_mode = 'barangay'
        if request.user.barangay:
            assigned_barangay = db_to_osm.get(request.user.barangay.name, request.user.barangay.name)
            
        barangays = [request.user.barangay] if request.user.barangay else []
        zones = Zone.objects.filter(barangay=request.user.barangay).order_by('name') if request.user.barangay else []
    else:
        barangays = Barangay.objects.all().order_by('name')
        zones = Zone.objects.all().order_by('name')
        
    land_uses = Household.LAND_USE_CHOICES
    hazards = Household.HAZARD_CHOICES
    
    demographic_flags = [
        ('is_pwd', 'PWD'),
        ('is_solo_parent', 'Solo Parent'),
        ('is_senior_citizen', 'Senior Citizen'),
    ]
    
    zone_map = {}
    for z in zones:
        b_id = str(z.barangay_id)
        if b_id not in zone_map:
            zone_map[b_id] = []
        zone_map[b_id].append({'id': z.id, 'name': z.name})

    return render(request, 'households/household_map.html', {
        'barangays': barangays,
        'land_uses': land_uses,
        'hazards': hazards,
        'demographic_flags': demographic_flags,
        'zone_map_json': json.dumps(zone_map),
        'boundary_mode': boundary_mode,
        'assigned_barangay': assigned_barangay,
    })

@login_required
@session_protected
def household_map_data(request):
    hazard_types = request.GET.getlist('hazard_types')
    if not hazard_types:
        hazard_types_str = request.GET.get('hazard_types')
        if hazard_types_str:
            hazard_types = hazard_types_str.split(',')
    
    demographic_flags = request.GET.getlist('demographic_flags')
    if not demographic_flags:
        demographic_flags_str = request.GET.get('demographic_flags')
        if demographic_flags_str:
            demographic_flags = demographic_flags_str.split(',')
    
    barangay_id = request.GET.get('barangay')
    zone_id = request.GET.get('zone')
    land_use = request.GET.get('land_use')
    
    if request.user.role == 'BARANGAY':
        if not request.user.barangay:
            return JsonResponse({'total_count': 0, 'unpinned_count': 0, 'households': []})
        barangay = request.user.barangay
        if barangay_id and str(barangay_id) != str(barangay.id):
            return JsonResponse({'total_count': 0, 'unpinned_count': 0, 'households': []})
    else:
        barangay = Barangay.objects.filter(id=barangay_id).first() if barangay_id else None
        
    zone = Zone.objects.filter(id=zone_id).first() if zone_id else None
    
    qs = get_vulnerable_households(
        hazard_types=hazard_types if hazard_types else None,
        demographic_flags=demographic_flags if demographic_flags else None,
        barangay=barangay,
        zone=zone
    )
    
    if land_use:
        qs = qs.filter(land_use=land_use)
        
    pinned_qs = qs.filter(latitude__isnull=False, longitude__isnull=False).select_related('barangay', 'zone')
    unpinned_count = qs.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True)).count()
    total_count = pinned_qs.count()
    
    data = []
    for h in pinned_qs:
        matched_flags = get_matched_demographic_flags(h, demographic_flags) if demographic_flags else []
        data.append({
            'id': h.id,
            'latitude': float(h.latitude),
            'longitude': float(h.longitude),
            'house_number': h.house_number,
            'address': h.address,
            'land_use': h.get_land_use_display(),
            'hazard_exposure': h.hazard_exposure,
            'hazard_exposure_display': h.get_hazard_exposure_display(),
            'flood_depth': h.flood_depth,
            'flood_frequency': h.flood_frequency,
            'zone_name': h.zone.name,
            'barangay_name': h.barangay.name,
            'matched_flags': matched_flags,
        })
        
    return JsonResponse({
        'unpinned_count': unpinned_count,
        'total_count': total_count,
        'households': data
    })

@login_required
@session_protected
def household_vulnerability_map(request):
    db_to_osm = {v: k for k, v in OSM_TO_DB_BARANGAY_NAME.items()}
    boundary_mode = 'municipal'
    assigned_barangay = None

    if request.user.role == 'BARANGAY':
        boundary_mode = 'barangay'
        if request.user.barangay:
            assigned_barangay = db_to_osm.get(request.user.barangay.name, request.user.barangay.name)

        barangays = [request.user.barangay] if request.user.barangay else []
        zones = Zone.objects.filter(barangay=request.user.barangay).order_by('name') if request.user.barangay else []
        flood_prone_areas = FloodProneArea.objects.filter(zone__barangay=request.user.barangay).select_related('zone', 'zone__barangay')
    else:
        barangays = Barangay.objects.all().order_by('name')
        zones = Zone.objects.all().order_by('name')
        flood_prone_areas = FloodProneArea.objects.all().select_related('zone', 'zone__barangay')
        
    zone_map = {}
    for z in zones:
        b_id = str(z.barangay_id)
        if b_id not in zone_map:
            zone_map[b_id] = []
        zone_map[b_id].append({'id': z.id, 'name': z.name})

    from households.models import WeatherSnapshot
    from households.vulnerability import get_barangay_weather_risk

    latest_snapshot = WeatherSnapshot.objects.filter(fetch_successful=True).order_by('-fetched_at').first()
    weather_fetched_at = latest_snapshot.fetched_at.isoformat() if latest_snapshot else ''

    weather_risks = {}
    barangay_stats = {}
    
    if request.user.role == 'BARANGAY':
        if request.user.barangay:
            osm_name = db_to_osm.get(request.user.barangay.name, request.user.barangay.name)
            weather_risks[osm_name] = get_barangay_weather_risk(request.user.barangay)
    else:
        for b in barangays:
            osm_name = db_to_osm.get(b.name, b.name)
            weather_risks[osm_name] = get_barangay_weather_risk(b)
            barangay_stats[osm_name] = {
                'total': b.households.count(),
                'flood_exposed': b.households.filter(hazard_exposure='FLOOD').count()
            }
            
    fp_areas_data = []
    for fpa in flood_prone_areas:
        fp_areas_data.append({
            'id': fpa.id,
            'latitude': float(fpa.latitude),
            'longitude': float(fpa.longitude),
            'description': fpa.description,
            'zone_name': fpa.zone.name,
            'barangay_name': fpa.zone.barangay.name
        })

    return render(request, 'households/household_vulnerability_map.html', {
        'barangays': barangays,
        'zone_map_json': json.dumps(zone_map),
        'boundary_mode': boundary_mode,
        'assigned_barangay': assigned_barangay,
        'weather_risks_json': json.dumps(weather_risks),
        'weather_fetched_at': weather_fetched_at,
        'barangay_stats_json': json.dumps(barangay_stats),
        'flood_prone_areas_json': json.dumps(fp_areas_data),
    })

@login_required
@session_protected
def household_vulnerability_data(request):
    return JsonResponse({'total_count': 0, 'households': []})

@login_required(login_url='login')
@session_protected
def edit_family_name(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    family = get_object_or_404(Family, id=family_id, household__barangay=request.user.barangay)
    if request.method == 'POST':
        new_name = request.POST.get('family_name', '').strip()
        if new_name:
            family.family_name = new_name
            family.save()
            messages.success(request, "Family name updated successfully.")
        else:
            messages.error(request, "Family name cannot be empty.")
    return redirect('family_detail', family_id=family.id)

@login_required(login_url='login')
@session_protected
def delete_household(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    household = get_object_or_404(Household, id=household_id, barangay=request.user.barangay)
    if request.method == 'POST':
        zone_id = household.zone.id
        household.delete()
        messages.success(request, "Household removed successfully.")
        return redirect('zone_detail', zone_id=zone_id)
    return redirect('household_detail', household_id=household_id)

@login_required(login_url='login')
@session_protected
def delete_family(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    family = get_object_or_404(Family, id=family_id, household__barangay=request.user.barangay)
    if request.method == 'POST':
        household_id = family.household.id
        family.delete()
        messages.success(request, "Family removed successfully.")
        return redirect('household_detail', household_id=household_id)
    return redirect('family_detail', family_id=family_id)

@login_required(login_url='login')
@session_protected
def delete_family_member(request, member_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    member = get_object_or_404(FamilyMember, id=member_id, family__household__barangay=request.user.barangay)
    if request.method == 'POST':
        family_id = member.family.id
        member.delete()
        messages.success(request, "Family member removed successfully.")
        return redirect('family_detail', family_id=family_id)
    return redirect('family_detail', family_id=member.family.id)


# ----------------- Import/Export Views -----------------

@login_required(login_url='login')
@session_protected
def import_members_upload(request, zone_id):
    """Step 1: Upload and parse Excel file for import."""
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    
    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    
    if request.method == 'POST':
        uploaded_file = request.FILES.get('excel_file')
        if not uploaded_file:
            messages.error(request, "Please select an Excel file to upload.")
            return render(request, 'households/import_upload.html', {'zone': zone})
        
        # Validate file extension
        if not uploaded_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, "Please upload a valid Excel file (.xlsx or .xls).")
            return render(request, 'households/import_upload.html', {'zone': zone})
        
        # Save uploaded file to temporary location
        temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
        try:
            with os.fdopen(temp_fd, 'wb') as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
            
            # Parse the Excel file
            importer = RBIFormAImporter(temp_path)
            success, messages_list = importer.parse()
            
            if not success:
                for msg in messages_list:
                    messages.error(request, msg)
                return render(request, 'households/import_upload.html', {'zone': zone})
            
            # Store parsed data in session for preview step
            request.session['import_data'] = {
                'header_data': importer.get_header_data(),
                'members_data': importer.get_members_data(),
                'warnings': importer.get_warnings(),
                'errors': importer.get_errors(),
                'zone_id': zone_id,
            }
            
            # Redirect to preview page
            return redirect('import_members_preview')
            
        finally:
            # Explicitly drop references to help release any lingering handles
            importer = None
            import gc
            gc.collect()

            # Retry deletion a few times to handle transient Windows file locks
            # (e.g. antivirus/Defender briefly scanning newly-written .xlsx files)
            for attempt in range(5):
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.2 * (attempt + 1))  # brief backoff: 0.2s, 0.4s, 0.6s, 0.8s
                    else:
                        logger.warning(f"Could not delete temp import file {temp_path} after retries; it will be cleaned up by the OS temp directory eventually.")
    
    return render(request, 'households/import_upload.html', {'zone': zone})


@login_required(login_url='login')
@session_protected
def import_members_preview(request):
    """Step 2: Preview and correct imported data before committing."""
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    
    import_data = request.session.get('import_data')
    if not import_data:
        messages.error(request, "No import data found. Please uploadExcel file first.")
        return redirect('barangay_dashboard')
    
    zone_id = import_data['zone_id']
    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    
    # Get available zones in the barangay for selection
    available_zones = Zone.objects.filter(barangay=request.user.barangay).order_by('name')
    
    # Get relationship choices
    relationship_choices = RELATIONSHIP_CHOICES
    civil_status_choices = CIVIL_STATUS_CHOICES
    
    # Suggest family name from first member's last name
    members_data = import_data['members_data']
    suggested_family_name = ""
    if members_data:
        head_last_name = members_data[0].get('last_name', '')
        if head_last_name:
            suggested_family_name = f"{head_last_name} Family"
    
    if request.method == 'POST':
        # Store corrections and proceed to commit
        corrected_data = {
            'zone_id': request.POST.get('zone_id', zone_id),
            'family_name': request.POST.get('family_name', suggested_family_name),
            'members': [],
        }
        
        for idx, member in enumerate(members_data):
            member_data = {
                'row_number': member['row_number'],
                'last_name': request.POST.get(f'last_name_{idx}', member.get('last_name', '')),
                'first_name': request.POST.get(f'first_name_{idx}', member.get('first_name', '')),
                'middle_name': request.POST.get(f'middle_name_{idx}', member.get('middle_name', '')),
                'suffix': request.POST.get(f'suffix_{idx}', member.get('suffix', '')),
                'birthplace': request.POST.get(f'birthplace_{idx}', member.get('birthplace', '')),
                'birthdate': member.get('birthdate'),  # Keep original date
                'sex': request.POST.get(f'sex_{idx}', member.get('sex', '')),
                'civil_status': request.POST.get(f'civil_status_{idx}', member.get('civil_status', '')),
                'citizenship': request.POST.get(f'citizenship_{idx}', member.get('citizenship', 'Filipino')),
                'occupation': request.POST.get(f'occupation_{idx}', member.get('occupation', '')),
                'relationship': request.POST.get(f'relationship_{idx}', member.get('relationship', '')),
                'is_pwd': request.POST.get(f'is_pwd_{idx}', 'off') == 'on',
                'is_solo_parent': request.POST.get(f'is_solo_parent_{idx}', 'off') == 'on',
                'is_out_of_school_youth': request.POST.get(f'is_out_of_school_youth_{idx}', 'off') == 'on',
                'is_out_of_school_children': request.POST.get(f'is_out_of_school_children_{idx}', 'off') == 'on',
                'is_indigenous': request.POST.get(f'is_indigenous_{idx}', 'off') == 'on',
                'is_senior_citizen': request.POST.get(f'is_senior_citizen_{idx}', 'off') == 'on',
                'include': request.POST.get(f'include_{idx}', 'on') == 'on',
            }
            corrected_data['members'].append(member_data)
        
        # Store corrected data in session
        request.session['import_corrected_data'] = corrected_data
        
        return redirect('import_members_commit')
    
    return render(request, 'households/import_preview.html', {
        'zone': zone,
        'available_zones': available_zones,
        'header_data': import_data['header_data'],
        'members_data': members_data,
        'warnings': import_data['warnings'],
        'errors': import_data['errors'],
        'relationship_choices': relationship_choices,
        'civil_status_choices': civil_status_choices,
        'suggested_family_name': suggested_family_name,
    })


@login_required(login_url='login')
@session_protected
def import_members_commit(request):
    """Step 3: Commit the imported data to create household, family, and members."""
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    
    corrected_data = request.session.get('import_corrected_data')
    if not corrected_data:
        messages.error(request, "No corrected import data found. Please start over.")
        return redirect('barangay_dashboard')
    
    zone_id = corrected_data['zone_id']
    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    
    if request.method == 'POST':
        # Confirm and commit
        try:
            with transaction.atomic():
                # Create Household
                household_address = corrected_data['family_name']
                household = Household.objects.create(
                    barangay=request.user.barangay,
                    zone=zone,
                    house_number=household_address,
                    land_use='RESIDENTIAL',  # Default, needs completion
                    hazard_exposure='NONE',  # Default, needs completion
                )
                
                # Create Family
                family = Family.objects.create(
                    household=household,
                    family_name=corrected_data['family_name'],
                )
                
                # Create FamilyMembers
                members_created = 0
                members_skipped = 0
                skipped_reasons = []
                
                for member_data in corrected_data['members']:
                    if not member_data.get('include'):
                        members_skipped += 1
                        skipped_reasons.append(f"Row {member_data['row_number']}: Excluded by user")
                        continue
                    
                    # Validate required fields
                    if not member_data.get('last_name') or not member_data.get('first_name') or not member_data.get('sex'):
                        members_skipped += 1
                        skipped_reasons.append(f"Row {member_data['row_number']}: Missing required fields")
                        continue
                    
                    if not member_data.get('relationship'):
                        members_skipped += 1
                        skipped_reasons.append(f"Row {member_data['row_number']}: Missing relationship")
                        continue
                    
                    # Convert birthdate from ISO string to date object if present
                    birthdate = None
                    if member_data.get('birthdate'):
                        try:
                            birthdate = date.fromisoformat(member_data['birthdate'])
                        except (ValueError, TypeError):
                            # Invalid date format, skip this field
                            pass
                    
                    # Create member
                    FamilyMember.objects.create(
                        family=family,
                        last_name=member_data['last_name'],
                        first_name=member_data['first_name'],
                        middle_name=member_data.get('middle_name', ''),
                        suffix=member_data.get('suffix', ''),
                        birthplace=member_data.get('birthplace', ''),
                        birthdate=birthdate,
                        sex=member_data['sex'],
                        civil_status=member_data.get('civil_status'),
                        citizenship=member_data.get('citizenship', 'Filipino'),
                        occupation=member_data.get('occupation', ''),
                        relationship=member_data['relationship'],
                        is_pwd=member_data.get('is_pwd', False),
                        is_solo_parent=member_data.get('is_solo_parent', False),
                        is_out_of_school_youth=member_data.get('is_out_of_school_youth', False),
                        is_out_of_school_children=member_data.get('is_out_of_school_children', False),
                        is_indigenous=member_data.get('is_indigenous', False),
                        is_senior_citizen=member_data.get('is_senior_citizen', False),
                    )
                    members_created += 1
                
                # Clear session data
                request.session.pop('import_data', None)
                request.session.pop('import_corrected_data', None)
                
                # Store results for summary page
                request.session['import_results'] = {
                    'household_id': household.id,
                    'family_id': family.id,
                    'households_created': 1,
                    'members_created': members_created,
                    'members_skipped': members_skipped,
                    'skipped_reasons': skipped_reasons,
                    'needs_completion': True,  # Flag that household needs additional data
                }
                
                return redirect('import_members_summary')
                
        except Exception as e:
            messages.error(request, f"Error during import: {str(e)}")
            return redirect('import_members_preview')
    
    return render(request, 'households/import_commit.html', {
        'zone': zone,
        'corrected_data': corrected_data,
    })


@login_required(login_url='login')
@session_protected
def import_members_summary(request):
    """Step 4: Show import summary and results."""
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")
    
    results = request.session.get('import_results')
    if not results:
        messages.error(request, "No import results found.")
        return redirect('barangay_dashboard')
    
    household_id = results['household_id']
    family_id = results['family_id']
    
    household = get_object_or_404(Household, id=household_id, barangay=request.user.barangay)
    family = get_object_or_404(Family, id=family_id, household__barangay=request.user.barangay)
    
    # Clear session results after displaying
    request.session.pop('import_results', None)
    
    return render(request, 'households/import_summary.html', {
        'household': household,
        'family': family,
        'results': results,
    })


@login_required
@session_protected
def export_household_excel(request, household_id):
    """Export a single household to Excel in RBI Form A format."""
    # Check permissions
    if request.user.role == 'BARANGAY':
        household = get_object_or_404(
            Household.objects.select_related('barangay', 'zone'),
            id=household_id,
            barangay=request.user.barangay
        )
    elif request.user.role in ('MSWDO', 'MSWDO_STAFF'):
        household = get_object_or_404(
            Household.objects.select_related('barangay', 'zone'),
            id=household_id
        )
    else:
        return HttpResponseForbidden("Access Denied")
    
    # Get the first/only family
    family = household.families.filter(is_active=True).first()
    if not family:
        messages.error(request, "No active family found for this household.")
        return redirect('household_detail' if request.user.role == 'BARANGAY' else 'household_info', household_id=household_id)
    
    # Generate Excel file
    exporter = RBIFormAExporter()
    workbook = exporter.generate_single_household(household, family)
    
    # Save to temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
    try:
        with os.fdopen(temp_fd, 'wb') as temp_file:
            workbook.save(temp_file)
        
        # Close workbook to release file handle
        workbook.close()
        
        # Read file and send as response
        with open(temp_path, 'rb') as f:
            file_content = f.read()
        
        response = HttpResponse(
            file_content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="RBI_Form_A_{household.house_number.replace(" ", "_")}.xlsx"'
        return response
        
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@login_required
@session_protected
def export_family_excel(request, family_id):
    """Export a single family to Excel in RBI Form A format."""
    # Check permissions
    if request.user.role == 'BARANGAY':
        family = get_object_or_404(
            Family.objects.select_related('household', 'household__barangay', 'household__zone'),
            id=family_id,
            household__barangay=request.user.barangay
        )
    elif request.user.role in ('MSWDO', 'MSWDO_STAFF'):
        family = get_object_or_404(
            Family.objects.select_related('household', 'household__barangay', 'household__zone'),
            id=family_id
        )
    else:
        return HttpResponseForbidden("Access Denied")
    
    # Generate Excel file
    exporter = RBIFormAExporter()
    workbook = exporter.generate_single_household(family.household, family)
    
    # Save to temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
    try:
        with os.fdopen(temp_fd, 'wb') as temp_file:
            workbook.save(temp_file)
        
        # Close workbook to release file handle
        workbook.close()
        
        # Read file and send as response
        with open(temp_path, 'rb') as f:
            file_content = f.read()
        
        response = HttpResponse(
            file_content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="RBI_Form_A_{family.family_name.replace(" ", "_")}.xlsx"'
        return response
        
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@login_required
@session_protected
def export_zone_households_excel(request, zone_id):
    """Export all households in a zone to Excel in RBI Form A format."""
    # Check permissions
    if request.user.role == 'BARANGAY':
        zone = get_object_or_404(
            Zone.objects.select_related('barangay'),
            id=zone_id,
            barangay=request.user.barangay
        )
        households = Household.objects.filter(zone=zone)
    elif request.user.role in ('MSWDO', 'MSWDO_STAFF'):
        zone = get_object_or_404(
            Zone.objects.select_related('barangay'),
            id=zone_id
        )
        households = Household.objects.filter(zone=zone)
    else:
        return HttpResponseForbidden("Access Denied")
    
    # Generate Excel file with multiple sheets
    exporter = RBIFormAExporter()
    workbook = exporter.generate_multiple_households(households)
    
    # Save to temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
    try:
        with os.fdopen(temp_fd, 'wb') as temp_file:
            workbook.save(temp_file)
        
        # Close workbook to release file handle
        workbook.close()
        
        # Read file and send as response
        with open(temp_path, 'rb') as f:
            file_content = f.read()
        
        response = HttpResponse(
            file_content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="RBI_Form_A_{zone.name.replace(" ", "_")}_All_Households.xlsx"'
        return response
        
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
