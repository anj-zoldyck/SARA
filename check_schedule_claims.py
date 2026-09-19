"""
Check all claims related to a schedule (including late scheduled claims).
Usage: python check_schedule_claims.py <schedule_id>
"""

import sqlite3
import sys

if len(sys.argv) < 2:
    print("Usage: python check_schedule_claims.py <schedule_id>")
    sys.exit(1)

schedule_id = sys.argv[1]

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

print("=" * 80)
print(f"ALL CLAIMS RELATED TO SCHEDULE {schedule_id}")
print("=" * 80)
print()

# Claims with schedule=schedule_id
print("1. CLAIMS WITH schedule=schedule_id:")
cursor.execute(f"""
    SELECT id, family_id, family_member_id, claim_type, claimed_at, is_late_scheduled_claim, original_schedule_id
    FROM distribution_aidclaim
    WHERE schedule_id = {schedule_id}
""")
claims = cursor.fetchall()
print(f"   Count: {len(claims)}")
for claim in claims:
    print(f"   - Claim {claim[0]}: family={claim[1]}, member={claim[2]}, type={claim[3]}, claimed_at={claim[4]}, late={claim[5]}, original_schedule={claim[6]}")

print()

# Claims with original_schedule=schedule_id (late scheduled claims)
print("2. CLAIMS WITH original_schedule=schedule_id (LATE SCHEDULED CLAIMS):")
cursor.execute(f"""
    SELECT id, family_id, family_member_id, claim_type, claimed_at, is_late_scheduled_claim, original_schedule_id
    FROM distribution_aidclaim
    WHERE original_schedule_id = {schedule_id}
""")
late_claims = cursor.fetchall()
print(f"   Count: {len(late_claims)}")
for claim in late_claims:
    print(f"   - Claim {claim[0]}: family={claim[1]}, member={claim[2]}, type={claim[3]}, claimed_at={claim[4]}, late={claim[5]}, original_schedule={claim[6]}")

print()

# Total combined
print("3. TOTAL CLAIMS (both regular + late scheduled):")
total = len(claims) + len(late_claims)
print(f"   Total: {total}")

print()
print("=" * 80)

conn.close()
