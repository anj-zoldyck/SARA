import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

print("=" * 80)
print("EVIDENCE EXTRACTION BEFORE DELETION")
print("=" * 80)
print()

# 1. Schedule 116 details
print("1. Schedule 116 Details:")
cursor.execute("""
    SELECT s.id, s.schedule_datetime, s.location, s.barangay_id, s.assistance_id, s.is_finished, s.finished_at, s.created_at
    FROM distribution_aidschedule s
    WHERE s.id = 116
""")
row = cursor.fetchone()
if row:
    print(f"   ID: {row[0]}")
    print(f"   schedule_datetime: {row[1]}")
    print(f"   location: {row[2]}")
    print(f"   barangay_id: {row[3]}")
    print(f"   assistance_id: {row[4]}")
    print(f"   is_finished: {row[5]}")
    print(f"   finished_at: {row[6]}")
    print(f"   created_at: {row[7]}")
    
    # Get barangay name
    cursor.execute("SELECT name FROM accounts_barangay WHERE id = ?", (row[3],))
    brgy = cursor.fetchone()
    if brgy:
        print(f"   barangay: {brgy[0]}")
print()

# 2. Schedule 117 details
print("2. Schedule 117 Details:")
cursor.execute("""
    SELECT s.id, s.schedule_datetime, s.location, s.barangay_id, s.assistance_id, s.is_finished, s.finished_at, s.created_at
    FROM distribution_aidschedule s
    WHERE s.id = 117
""")
row = cursor.fetchone()
if row:
    print(f"   ID: {row[0]}")
    print(f"   schedule_datetime: {row[1]}")
    print(f"   location: {row[2]}")
    print(f"   barangay_id: {row[3]}")
    print(f"   assistance_id: {row[4]}")
    print(f"   is_finished: {row[5]}")
    print(f"   finished_at: {row[6]}")
    print(f"   created_at: {row[7]}")
    
    # Get barangay name
    cursor.execute("SELECT name FROM accounts_barangay WHERE id = ?", (row[3],))
    brgy = cursor.fetchone()
    if brgy:
        print(f"   barangay: {brgy[0]}")
print()

# 3. Beneficiary list for Schedule 116
print("3. Beneficiary List for Schedule 116:")
cursor.execute("""
    SELECT gb.id, gb.family_id, gb.family_member_id, gb.household_id
    FROM distribution_generatedbeneficiary gb
    JOIN distribution_generatedbeneficiarylist gbl ON gb.beneficiary_list_id = gbl.id
    WHERE gbl.schedule_id = 116
""")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    if r[2]:  # family_member
        cursor.execute("SELECT first_name, last_name FROM households_familymember WHERE id = ?", (r[2],))
        member = cursor.fetchone()
        if member:
            print(f"   ID {r[0]}: member_id={r[2]}, name={member[0]} {member[1]}")
    elif r[1]:  # family
        cursor.execute("SELECT family_name FROM households_family WHERE id = ?", (r[1],))
        family = cursor.fetchone()
        if family:
            print(f"   ID {r[0]}: family_id={r[1]}, family={family[0]}")
    else:
        print(f"   ID {r[0]}: household_id={r[3]}")
print()

# 4. Beneficiary list for Schedule 117
print("4. Beneficiary List for Schedule 117:")
cursor.execute("""
    SELECT gb.id, gb.family_id, gb.family_member_id, gb.household_id
    FROM distribution_generatedbeneficiary gb
    JOIN distribution_generatedbeneficiarylist gbl ON gb.beneficiary_list_id = gbl.id
    WHERE gbl.schedule_id = 117
""")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    if r[2]:  # family_member
        cursor.execute("SELECT first_name, last_name FROM households_familymember WHERE id = ?", (r[2],))
        member = cursor.fetchone()
        if member:
            print(f"   ID {r[0]}: member_id={r[2]}, name={member[0]} {member[1]}")
    elif r[1]:  # family
        cursor.execute("SELECT family_name FROM households_family WHERE id = ?", (r[1],))
        family = cursor.fetchone()
        if family:
            print(f"   ID {r[0]}: family_id={r[1]}, family={family[0]}")
    else:
        print(f"   ID {r[0]}: household_id={r[3]}")
print()

# 5. Claim 285 full details
print("5. Claim 285 Full Details:")
cursor.execute("""
    SELECT id, family_id, family_member_id, assistance_id, claim_type, claimed_at, 
           amount, is_late_scheduled_claim, original_schedule_id, is_exported, created_by_id
    FROM distribution_aidclaim
    WHERE id = 285
""")
row = cursor.fetchone()
if row:
    print(f"   id: {row[0]}")
    print(f"   family_id: {row[1]}")
    print(f"   family_member_id: {row[2]}")
    print(f"   assistance_id: {row[3]}")
    print(f"   claim_type: {row[4]}")
    print(f"   claimed_at: {row[5]}")
    print(f"   amount: {row[6]}")
    print(f"   is_late_scheduled_claim: {row[7]}")
    print(f"   original_schedule_id: {row[8]}")
    print(f"   is_exported: {row[9]}")
    print(f"   created_by_id: {row[10]}")
    
    # Get family member name
    if row[2]:
        cursor.execute("SELECT first_name, last_name FROM households_familymember WHERE id = ?", (row[2],))
        member = cursor.fetchone()
        if member:
            print(f"   family_member: {member[0]} {member[1]}")

print()
print("=" * 80)
print("END OF EVIDENCE EXTRACTION")
print("=" * 80)

conn.close()
