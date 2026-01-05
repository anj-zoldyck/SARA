from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.contrib import messages
from .models import User, Household, Zone, Family, FamilyMember
from .forms import HouseholdForm, FamilyForm, FamilyMemberForm
def landing_page(request):
    return render(request, 'accounts/landing.html')

def logout_view(request):
    logout(request)
    return redirect('login')

def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, "Account is deactivated.")
            else:
                login(request, user)
                if user.role == 'MSWDO':
                    return redirect('mswdo_dashboard')
                else:
                    return redirect('barangay_dashboard')
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'accounts/login.html')

@login_required
def mswdo_dashboard(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangays = User.objects.filter(role='BARANGAY')
    return render(
        request,
        'accounts/mswdo_dashboard.html',
        {'barangays': barangays}
    )


@login_required
def create_barangay(request):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    if request.method == 'POST':
        User.objects.create_user(
            username=request.POST['username'],
            password=request.POST['password'],
            role='BARANGAY',
            barangay=request.POST['barangay']
        )
        return redirect('mswdo_dashboard')

    return render(request, 'accounts/create_barangay.html')

@login_required
def deactivate_barangay(request, user_id):
    if request.user.role != 'MSWDO':
        return HttpResponseForbidden("Access Denied")

    barangay = User.objects.get(id=user_id)
    barangay.is_active = False
    barangay.save()

    return redirect('mswdo_dashboard')

@login_required
def barangay_dashboard(request):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    barangay_name = request.user.barangay
    zones = Zone.objects.filter(barangay=barangay_name)  # <-- Here

    return render(request, 'barangay/dashboard.html', {
        'barangay': barangay_name,
        'zones': zones
    })

@login_required
def zone_detail(request, zone_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    zone = get_object_or_404(Zone, id=zone_id, barangay=request.user.barangay)
    households = Household.objects.filter(zone=zone)

    return render(request, 'barangay/zone_detail.html', {
        'zone': zone,
        'households': households
    })

#household detail
@login_required
def household_detail(request, household_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    household = get_object_or_404(
        Household,
        id=household_id,
        barangay=request.user.barangay
    )

    families = household.families.all()

    return render(request, 'barangay/household_detail.html', {
        'household': household,
        'families': families
    })


#add household
@login_required
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

    return render(request, 'barangay/add_household.html', {
        'form': form,
        'zone': zone
    })

@login_required
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

    return render(request, 'barangay/add_family.html', {
        'form': form,
        'household': household
    })

#family detail
@login_required
def family_detail(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(
        Family,
        id=family_id,
        household__barangay=request.user.barangay
    )

    members = family.members.all()

    return render(request, 'barangay/family_detail.html', {
        'family': family,
        'members': members
    })

#add family member
@login_required
def add_family_member(request, family_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    family = get_object_or_404(
        Family,
        id=family_id,
        household__barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = FamilyMemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.family = family
            member.save()
            return redirect('family_detail', family_id=family.id)
    else:
        form = FamilyMemberForm()

    return render(request, 'barangay/add_member.html', {
        'form': form,
        'family': family
    })

#edit family member
@login_required
def edit_family_member(request, member_id):
    if request.user.role != 'BARANGAY':
        return HttpResponseForbidden("Access Denied")

    member = get_object_or_404(
        FamilyMember,
        id=member_id,
        family__household__barangay=request.user.barangay
    )

    if request.method == 'POST':
        form = FamilyMemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            return redirect('family_detail', family_id=member.family.id)
    else:
        form = FamilyMemberForm(instance=member)

    return render(request, 'barangay/edit_member.html', {
        'form': form,
        'member': member
    })


