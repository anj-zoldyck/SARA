from django.utils import timezone
from .models import AidSchedule
from django.db.models import Q

def get_active_aid_schedule():
    now = timezone.now()

    return AidSchedule.objects.filter(
        is_active=True,
        schedule_datetime__lte=now
    ).filter(
        Q(end_datetime__gte=now) | Q(end_datetime__isnull=True)
    ).order_by('-schedule_datetime').first()

def get_active_schedule():
    now = timezone.now()

    return AidSchedule.objects.filter(
        schedule_datetime__lte=now,
        end_datetime__gte=now,
        is_active=True
    ).order_by('-schedule_datetime').first()