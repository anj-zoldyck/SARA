
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

from django.db import transaction
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm, SeniorCitizenProfileForm, SoloParentProfileForm, PWDProfileForm
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
def barangay_list(request):

    barangays = Barangay.objects.all().order_by('name')

    return render(request, 'households/barangay_list.html', {
        'barangays': barangays,
    })


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


@login_required
@session_protected
@mswdo_or_staff_required
def family_members(request, family_id):

    family = get_object_or_404(Family.objects.select_related('household', 'household__zone', 'household__barangay'), id=family_id)

    members = family.members.all().order_by('first_name', 'last_name')  # or use select_related if needed

    return render(request, 'households/family_members.html', {
        'family': family,
        'members': members,
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
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(
        Family,
        id=family_id,
        household__barangay=request.user.barangay
    )

    members = family.members.all()

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
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden('Access Denied')

    member = get_object_or_404(
        FamilyMember,
        id=member_id,
        family__household__barangay=request.user.barangay
    )

    claims = AidClaim.objects.filter(
        Q(family_member=member) | Q(family=member.family, family_member__isnull=True)
    ).select_related('assistance__program', 'assistance__aid_category').order_by('-claimed_at')

    return render(request, 'households/partials/member_detail_modal.html', {
        'member': member,
        'claims': claims
    })
