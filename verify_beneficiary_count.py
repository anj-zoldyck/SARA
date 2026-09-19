"""
Direct database query to verify ALL GeneratedBeneficiary entries for a schedule's list.
Usage: python verify_beneficiary_count.py <schedule_id>
"""

import sqlite3
import sys

if len(sys.argv) < 2:
    print("Usage: python verify_beneficiary_count.py <schedule_id>")
    sys.exit(1)

schedule_id = sys.argv[1]

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

print("=" * 80)
print(f"RAW BENEFICIARY COUNT FOR SCHEDULE {schedule_id}")
print("=" * 80)
print()

# Get beneficiary list ID for this schedule
cursor.execute(f"""
    SELECT id FROM distribution_generatedbeneficiarylist
    WHERE schedule_id = {schedule_id}
""")
result = cursor.fetchone()

if not result:
    print(f"No beneficiary list found for schedule {schedule_id}")
    conn.close()
    sys.exit(1)

ben_list_id = result[0]
print(f"Beneficiary List ID: {ben_list_id}")
print()

# Count ALL entries in the beneficiary list (no filters)
cursor.execute(f"""
    SELECT COUNT(*) FROM distribution_generatedbeneficiary
    WHERE beneficiary_list_id = {ben_list_id}
""")
total_count = cursor.fetchone()[0]
print(f"TOTAL entries in beneficiary list (no filters): {total_count}")
print()

# Count entries with family_member (individual-based)
cursor.execute(f"""
    SELECT COUNT(*) FROM distribution_generatedbeneficiary
    WHERE beneficiary_list_id = {ben_list_id} AND family_member_id IS NOT NULL
""")
individual_count = cursor.fetchone()[0]
print(f"Entries with family_member (individual-based): {individual_count}")
print()

# Count entries with family (family-based)
cursor.execute(f"""
    SELECT COUNT(*) FROM distribution_generatedbeneficiary
    WHERE beneficiary_list_id = {ben_list_id} AND family_id IS NOT NULL
""")
family_count = cursor.fetchone()[0]
print(f"Entries with family (family-based): {family_count}")
print()

# List ALL entries with details
print("ALL entries in beneficiary list:")
cursor.execute(f"""
    SELECT id, family_id, family_member_id 
    FROM distribution_generatedbeneficiary
    WHERE beneficiary_list_id = {ben_list_id}
""")
entries = cursor.fetchall()
for entry in entries:
    if entry[2]:  # family_member_id
        print(f"  - Entry {entry[0]}: family_member_id={entry[2]}, family_id={entry[1]}")
    elif entry[1]:  # family_id
        print(f"  - Entry {entry[0]}: family_id={entry[1]}, family_member_id=NULL")
    else:
        print(f"  - Entry {entry[0]}: family_id=NULL, family_member_id=NULL (ORPHANED)")

print()
print("=" * 80)

conn.close()
