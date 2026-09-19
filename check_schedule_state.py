"""
Check the current state of a schedule for debugging Test 2.
Usage: python check_schedule_state.py <schedule_id>
"""

import sqlite3
import sys

if len(sys.argv) < 2:
    print("Usage: python check_schedule_state.py <schedule_id>")
    sys.exit(1)

schedule_id = sys.argv[1]

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

print("=" * 80)
print(f"SCHEDULE STATE CHECK FOR SCHEDULE {schedule_id}")
print("=" * 80)
print()

# Get schedule details
print("1. SCHEDULE DETAILS:")
cursor.execute(f"""
    SELECT id, is_finished, finished_at, finish_reason, schedule_datetime, per_beneficiary_amount
    FROM distribution_aidschedule
    WHERE id = {schedule_id}
""")
row = cursor.fetchone()
if row:
    print(f"   ID: {row[0]}")
    print(f"   is_finished: {row[1]}")
    print(f"   finished_at: {row[2]}")
    print(f"   finish_reason: {row[3]}")
    print(f"   schedule_datetime: {row[4]}")
    print(f"   per_beneficiary_amount: {row[5]}")
else:
    print(f"   Schedule {schedule_id} not found")
    conn.close()
    sys.exit(1)

print()

# Get beneficiary list
print("2. BENEFICIARY LIST:")
cursor.execute(f"""
    SELECT id FROM distribution_generatedbeneficiarylist
    WHERE schedule_id = {schedule_id}
""")
ben_list_row = cursor.fetchone()
if ben_list_row:
    ben_list_id = ben_list_row[0]
    print(f"   Beneficiary List ID: {ben_list_id}")
    
    cursor.execute(f"""
        SELECT COUNT(*) FROM distribution_generatedbeneficiary
        WHERE beneficiary_list_id = {ben_list_id}
    """)
    total_bens = cursor.fetchone()[0]
    print(f"   Total beneficiaries on list: {total_bens}")
else:
    print(f"   No beneficiary list found for this schedule")
    ben_list_id = None
    total_bens = 0

print()

# Get claims for this schedule
print("3. CLAIMS FOR THIS SCHEDULE:")
cursor.execute(f"""
    SELECT id, family_id, family_member_id, claim_type, claimed_at, is_late_scheduled_claim, original_schedule_id
    FROM distribution_aidclaim
    WHERE schedule_id = {schedule_id}
""")
claims = cursor.fetchall()
print(f"   Total claims: {len(claims)}")
for claim in claims:
    print(f"   - Claim {claim[0]}: family={claim[1]}, member={claim[2]}, type={claim[3]}, claimed_at={claim[4]}, late={claim[5]}, original_schedule={claim[6]}")

print()

# Check if schedule should be finished based on beneficiary count
print("4. SHOULD SCHEDULE BE FINISHED?")
if total_bens > 0:
    claimed_count = len(claims)
    print(f"   Beneficiaries on list: {total_bens}")
    print(f"   Claims recorded: {claimed_count}")
    if claimed_count >= total_bens:
        print(f"   → YES: All beneficiaries claimed (or more)")
    else:
        print(f"   → NO: {total_bens - claimed_count} beneficiaries still unclaimed")
else:
    print(f"   Cannot determine (no beneficiary list)")

print()
print("=" * 80)

conn.close()
