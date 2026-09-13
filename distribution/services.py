from django.utils import timezone
from .models import AidSchedule
from django.db.models import Q

def is_barangay_delegable(schedule):
    """
    Check if a schedule is eligible for barangay delegation.
    A schedule is delegable if:
    - The program allows barangay delegation
    - The schedule is scoped to a single barangay (not municipal-wide)
    """
    return (
        schedule.assistance.program.allows_barangay_delegation
        and schedule.barangay_id is not None
    )

def get_active_aid_schedule():
    now = timezone.now()

    return AidSchedule.objects.filter(
        is_active=True,
        is_finished=False,
        schedule_datetime__lte=now
    ).order_by('-schedule_datetime').first()

def get_active_schedule():
    now = timezone.now()

    return AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        is_finished=False,
        is_active=True
    ).order_by('-schedule_datetime').first()

def is_staff_assigned_to_scan(user, schedule, household=None):
    """
    Returns True if `user` is allowed to process claims for `household`
    under `schedule`. Logic:
    - MSWDO role: always allowed
    - MSWDO_STAFF role: if no assignments exist, open access; otherwise must have matching assignment
    - BARANGAY role: NEVER falls back to open access - must have explicit assignment AND schedule must be delegable
    """
    from .models import AssignedTo
    
    assignments = AssignedTo.objects.filter(schedule=schedule)
    
    if user.role == 'MSWDO':
        return True
    
    if user.role == 'MSWDO_STAFF':
        if not assignments.exists():
            return True  # existing open-access fallback, unchanged
        if household is None:
            return assignments.filter(staff=user).exists()
        
        barangay = household.barangay
        zone = household.zone
        
        return assignments.filter(
            schedule=schedule,
            staff=user
        ).filter(
            Q(barangay__isnull=True) | Q(barangay=barangay)
        ).filter(
            Q(zone__isnull=True) | Q(zone=zone)
        ).exists()
    
    if user.role == 'BARANGAY':
        # NEVER fall back to open access — must have an explicit row
        if not is_barangay_delegable(schedule):
            return False
        return assignments.filter(
            staff=user, barangay=user.barangay
        ).exists()
    
    return False