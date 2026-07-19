from django.utils import timezone
from .models import AidSchedule
from django.db.models import Q

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
    - If the schedule has NO AssignedTo records at all, return True
      (open access — this feature is additive/optional, matching the
      same fallback pattern used for the beneficiary-list restriction).
    - If assignments exist, the user must have an AssignedTo record
      matching the household's barangay, AND either matching the
      household's zone specifically OR have a barangay-wide assignment
      (zone=None) for that barangay.
    """
    from .models import AssignedTo
    
    # 1. If schedule has no assignments at all, it's open to all MSWDO_STAFF
    if not AssignedTo.objects.filter(schedule=schedule).exists():
        return True
        
    # 2. If no household is provided, just check if the user has ANY assignment for this schedule.
    if household is None:
        return AssignedTo.objects.filter(schedule=schedule, staff=user).exists()
        
    # 3. Schedule has assignments, so user must have a matching one
    # Note: household.zone could be None, which is fine, we check for exact match or zone=None
    
    barangay = household.barangay
    zone = household.zone
    
    # User must have an assignment for this schedule and barangay
    # AND (assignment.zone is None OR assignment.zone == household.zone)
    return AssignedTo.objects.filter(
        schedule=schedule,
        staff=user,
        barangay=barangay
    ).filter(
        Q(zone__isnull=True) | Q(zone=zone)
    ).exists()