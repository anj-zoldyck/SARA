"""
Get ground truth for a schedule: beneficiary list count vs claim count.
Usage: python get_ground_truth.py <schedule_id>
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sara.settings')
django.setup()

from distribution.models import AidSchedule, GeneratedBeneficiary, AidClaim

if len(os.sys.argv) < 2:
    print("Usage: python get_ground_truth.py <schedule_id>")
    os.sys.exit(1)

schedule_id = int(os.sys.argv[1])

schedule = AidSchedule.objects.get(id=schedule_id)

print("=" * 80)
print(f"GROUND TRUTH FOR SCHEDULE {schedule_id}")
print("=" * 80)
print()

print(f"Schedule:")
print(f"  ID: {schedule.id}")
print(f"  is_finished: {schedule.is_finished}")
print(f"  finished_at: {schedule.finished_at}")
print(f"  finish_reason: {schedule.finish_reason}")
print(f"  beneficiary_type: {schedule.assistance.beneficiary_type}")
print()

if not hasattr(schedule, 'beneficiary_list') or not schedule.beneficiary_list:
    print("ERROR: No beneficiary list found for this schedule")
    os.sys.exit(1)

ben_list = schedule.beneficiary_list

print(f"Beneficiary List ID: {ben_list.id}")
print()

# Count beneficiaries based on beneficiary type
if schedule.assistance.beneficiary_type == 'individual':
    total_bens = ben_list.entries.filter(family_member__isnull=False).count()
    print(f"Total beneficiaries (individual-based): {total_bens}")
    
    # List all beneficiaries
    print("\nBeneficiary list entries:")
    for entry in ben_list.entries.filter(family_member__isnull=False).select_related('family_member'):
        print(f"  - Member {entry.family_member_id}: {entry.family_member.first_name} {entry.family_member.last_name}")
elif schedule.assistance.beneficiary_type == 'family':
    total_bens = ben_list.entries.filter(family__isnull=False).count()
    print(f"Total beneficiaries (family-based): {total_bens}")
    
    # List all beneficiaries
    print("\nBeneficiary list entries:")
    for entry in ben_list.entries.filter(family__isnull=False).select_related('family'):
        print(f"  - Family {entry.family_id}: {entry.family.family_name}")

print()

# Count claims - both regular (schedule=schedule) and late (original_schedule=schedule)
regular_claims = AidClaim.objects.filter(schedule=schedule)
late_claims = AidClaim.objects.filter(original_schedule=schedule)

print(f"Regular claims (schedule={schedule_id}): {regular_claims.count()}")
for claim in regular_claims.select_related('family_member', 'family'):
    if claim.family_member:
        print(f"  - Claim {claim.id}: Member {claim.family_member_id} ({claim.family_member.first_name} {claim.family_member.last_name}), type={claim.claim_type}")
    else:
        print(f"  - Claim {claim.id}: Family {claim.family_id} ({claim.family.family_name}), type={claim.claim_type}")

print()

print(f"Late scheduled claims (original_schedule={schedule_id}): {late_claims.count()}")
for claim in late_claims.select_related('family_member', 'family'):
    if claim.family_member:
        print(f"  - Claim {claim.id}: Member {claim.family_member_id} ({claim.family_member.first_name} {claim.family_member.last_name}), type={claim.claim_type}")
    else:
        print(f"  - Claim {claim.id}: Family {claim.family_id} ({claim.family.family_name}), type={claim.claim_type}")

print()

total_claims = regular_claims.count() + late_claims.count()
print(f"TOTAL CLAIMS (regular + late): {total_claims}")
print()

print("=" * 80)
print("SUMMARY:")
print(f"  Total beneficiaries: {total_bens}")
print(f"  Total claims: {total_claims}")
print(f"  Unclaimed: {total_bens - total_claims}")
print(f"  Should be finished: {total_claims >= total_bens}")
print("=" * 80)
