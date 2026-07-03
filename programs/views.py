
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

from accounts.forms import UserEditForm, CreateUserForm
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
def program_list(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    programs = Program.objects.prefetch_related(
        'aid_categories',
        'assistances__aid_category'
    ).all().order_by('name')

    return render(request, 'programs/program_list.html', {
        'programs': programs,
    })


@login_required
@session_protected
def add_program(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = ProgramForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Program added successfully.")
            return redirect('program_list')
    else:
        form = ProgramForm()

    return render(request, 'accounts/add_program.html', {'form': form})


@login_required
@session_protected
def edit_program(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)

    if request.method == 'POST':
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(request, f"Program '{program.name}' updated successfully.")
            return redirect('program_list')
    else:
        form = ProgramForm(instance=program)

    return render(request, 'accounts/edit_program.html', {
        'form': form,
        'program': program,
    })


@login_required
@session_protected
def toggle_program(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)
    program.is_active = not program.is_active
    program.save()

    status = "activated" if program.is_active else "deactivated"
    messages.success(request, f"Program '{program.name}' {status}.")
    return redirect('program_list')


@login_required
@session_protected
def add_aid_category(request, program_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    program = get_object_or_404(Program, id=program_id)

    if request.method == 'POST':
        form = AidCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Aid category added successfully.")
            return redirect('program_list')
    else:
        form = AidCategoryForm(initial={'program': program})

    return render(request, 'accounts/add_aid_category.html', {
        'form': form,
        'program': program,
    })


@login_required
@session_protected
def add_assistance(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        form = AssistanceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Assistance entry added successfully.")
            return redirect('program_list')
    else:
        form = AssistanceForm()

    return render(request, 'accounts/add_assistance.html', {'form': form})


@login_required
@session_protected
def toggle_assistance(request, assistance_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(Assistance, id=assistance_id)
    assistance.is_active = not assistance.is_active
    assistance.save()

    status = "activated" if assistance.is_active else "deactivated"
    messages.success(request, f"Assistance '{assistance}' {status}.")
    return redirect('program_list')


@login_required
@session_protected
def edit_assistance(request, assistance_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    assistance = get_object_or_404(
        Assistance.objects.select_related('program', 'aid_category'),
        id=assistance_id
    )

    if request.method == 'POST':
        program_id     = request.POST.get('program')
        aid_category_id = request.POST.get('aid_category')
        beneficiary_type = request.POST.get('beneficiary_type')
        minimum_age    = request.POST.get('minimum_age') or None
        is_active      = request.POST.get('is_active') == 'on'

        # Validate
        if not all([program_id, aid_category_id, beneficiary_type]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('program_list')

        try:
            aid_category = AidCategory.objects.get(
                id=aid_category_id,
                program_id=program_id
            )
        except AidCategory.DoesNotExist:
            messages.error(request, "Invalid category for the selected program.")
            return redirect('program_list')

        assistance.aid_category      = aid_category
        assistance.program_id        = program_id
        assistance.beneficiary_type  = beneficiary_type
        assistance.minimum_age       = minimum_age
        assistance.is_active         = is_active
        assistance.save()

        messages.success(request, f"Assistance '{assistance}' updated successfully.")

    return redirect('program_list')

