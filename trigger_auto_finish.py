"""
Manually trigger auto-finish check for a schedule.
Usage: python trigger_auto_finish.py <schedule_id>
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sara.settings')
django.setup()

from distribution.models import AidSchedule
from distribution.schedule_utils import check_and_auto_finish_schedule
from accounts.models import User

if len(os.sys.argv) < 2:
    print("Usage: python trigger_auto_finish.py <schedule_id>")
    os.sys.exit(1)

schedule_id = int(os.sys.argv[1])

schedule = AidSchedule.objects.get(id=schedule_id)
print(f"Schedule {schedule_id}:")
print(f"  is_finished: {schedule.is_finished}")
print(f"  finished_at: {schedule.finished_at}")
print(f"  beneficiary_type: {schedule.assistance.beneficiary_type}")

# Get a user for audit logging
user = User.objects.filter(role='MSWDO_STAFF').first()
if not user:
    user = User.objects.first()

print(f"\nTriggering auto-finish check...")
result = check_and_auto_finish_schedule(schedule, user)

print(f"Result: {result}")
print(f"\nAfter check:")
schedule.refresh_from_db()
print(f"  is_finished: {schedule.is_finished}")
print(f"  finished_at: {schedule.finished_at}")
print(f"  finish_reason: {schedule.finish_reason}")
