
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
@mswdo_or_staff_required
def aid_reports(request):

    selected_barangay = request.GET.get('barangay')

    schedules = AidSchedule.objects.select_related(
    'assistance', 'assistance__program', 'assistance__aid_category', 'barangay'
        ).all().order_by('-schedule_datetime')

    if selected_barangay:
        schedules = schedules.filter(barangay_id=selected_barangay)

    # Attach claims per schedule
    for sched in schedules:
        sched.claims = AidClaim.objects.filter(
            schedule=sched          #filter by schedule directly
        ).select_related(
            'family',
            'family_member',
            'family__household',
            'family__household__barangay',
            'assistance',
            'assistance__aid_category',
        )

    barangays = Barangay.objects.all()

    return render(request, 'reports/aid_reports.html', {
        'schedules': schedules,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
        'now': timezone.now(),
    })


