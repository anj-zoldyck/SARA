"""
Shared utility functions for schedule management.
"""

from django.utils import timezone
from django.db.models import Q
from core.audit_utils import log_action


def check_and_auto_finish_schedule(schedule, user):
    """
    Check if all beneficiaries on the schedule's list have been claimed.
    If so, mark the schedule as finished automatically.
    
    This is used by:
    - scan_rfid (online distribution kiosk)
    - reconcile_claims_import (offline claim reconciliation)
    - import_full_offline_sync (full offline sync)
    
    Args:
        schedule: AidSchedule instance
        user: User instance (for audit logging)
    
    Returns:
        bool: True if schedule was just marked as finished, False otherwise
    """
    if not hasattr(schedule, 'beneficiary_list'):
        return False
    
    # Don't auto-finish if already finished
    if schedule.is_finished:
        return False
    
    ben_list = schedule.beneficiary_list
    assistance = schedule.assistance
    
    if assistance.beneficiary_type == 'family':
        # Family-based: check if all families on the list have claims
        total_bens = ben_list.entries.filter(family__isnull=False).count()
        from distribution.models import AidClaim
        # Include both regular claims (schedule=schedule) and late scheduled claims (original_schedule=schedule)
        claimed_families = AidClaim.objects.filter(
            Q(schedule=schedule) | Q(original_schedule=schedule)
        ).values('family').distinct().count()
        
        if total_bens > 0 and claimed_families >= total_bens:
            schedule.is_finished = True
            schedule.finished_at = timezone.now()
            schedule.finish_reason = 'COMPLETED'
            schedule.save()
            log_action(user, 'SCHEDULE_AUTO_FINISHED', target=schedule, 
                      description=f"Auto finished schedule {schedule.id} (all beneficiaries claimed)")
            return True
            
    elif assistance.beneficiary_type == 'individual':
        # Individual-based: check if all members on the list have claims
        from distribution.models import AidClaim
        # Include both regular claims (schedule=schedule) and late scheduled claims (original_schedule=schedule)
        claimed_member_ids = set(AidClaim.objects.filter(
            Q(schedule=schedule) | Q(original_schedule=schedule),
            family_member__isnull=False
        ).values_list('family_member_id', flat=True))
        
        is_finished = True
        for entry in ben_list.entries.filter(family_member__isnull=False):
            if entry.family_member_id not in claimed_member_ids:
                is_finished = False
                break
        
        if is_finished and ben_list.entries.filter(family_member__isnull=False).exists():
            schedule.is_finished = True
            schedule.finished_at = timezone.now()
            schedule.finish_reason = 'COMPLETED'
            schedule.save()
            log_action(user, 'SCHEDULE_AUTO_FINISHED', target=schedule,
                      description=f"Auto finished schedule {schedule.id} (all beneficiaries claimed)")
            return True
    
    return False
