import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# UTC range: Sep 6 00:00 PHT = Sep 5 16:00 UTC, Sep 13 23:59:59 PHT = Sep 13 15:59:59 UTC
start_utc = '2026-09-05 16:00:00'
end_utc = '2026-09-13 15:59:59'

print("=" * 60)
print("DRY RUN: Records for deletion (Sep 6-13, 2026 PH time)")
print("=" * 60)
print(f"UTC Range: {start_utc} to {end_utc}")
print()

# 1. AidSchedule (schedule_datetime in range)
print("1. AidSchedule (schedule_datetime in range):")
cursor.execute(f"SELECT id, schedule_datetime FROM distribution_aidschedule WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: {r[1]}")
print()

# 2. AidClaim (claimed_at in range)
print("2. AidClaim (claimed_at in range):")
cursor.execute(f"SELECT id, claimed_at, claim_type, original_schedule_id FROM distribution_aidclaim WHERE claimed_at >= '{start_utc}' AND claimed_at <= '{end_utc}'")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: {r[1]}, type={r[2]}, orig_sched={r[3]}")
print()

# 3. AidClaim (original_schedule in range, but claimed_at outside - AMBIGUOUS)
print("3. AidClaim (orig_sched in range, claimed_at outside - AMBIGUOUS):")
cursor.execute(f"SELECT id, claimed_at, claim_type, original_schedule_id FROM distribution_aidclaim WHERE original_schedule_id IN (SELECT id FROM distribution_aidschedule WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}') AND (claimed_at < '{start_utc}' OR claimed_at > '{end_utc}')")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: {r[1]}, type={r[2]}, orig_sched={r[3]}")
print()

# 4. GeneratedBeneficiaryList (via schedule FK)
print("4. GeneratedBeneficiaryList (via schedule FK):")
cursor.execute(f"SELECT id, schedule_id, generated_at FROM distribution_generatedbeneficiarylist WHERE schedule_id IN (SELECT id FROM distribution_aidschedule WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}')")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: schedule={r[1]}, generated={r[2]}")
print()

# 5. GeneratedBeneficiary (via schedule FK)
print("5. GeneratedBeneficiary (via schedule FK):")
cursor.execute(f"SELECT id, beneficiary_list_id FROM distribution_generatedbeneficiary WHERE beneficiary_list_id IN (SELECT id FROM distribution_generatedbeneficiarylist WHERE schedule_id IN (SELECT id FROM distribution_aidschedule WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'))")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
if len(rows) <= 50:
    for r in rows:
        print(f"   ID {r[0]}: list={r[1]}")
else:
    print(f"   (First 50 of {len(rows)})")
    for r in rows[:50]:
        print(f"   ID {r[0]}: list={r[1]}")
print()

# 6. AssignedTo (via schedule FK)
print("6. AssignedTo (via schedule FK):")
cursor.execute(f"SELECT id, schedule_id FROM distribution_assignedto WHERE schedule_id IN (SELECT id FROM distribution_aidschedule WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}')")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: schedule={r[1]}")
print()

# 7. BeneficiaryBackupDownload (downloaded_at in range)
print("7. BeneficiaryBackupDownload (downloaded_at in range):")
cursor.execute(f"SELECT id, schedule_id, downloaded_at FROM distribution_beneficiarybackupdownload WHERE downloaded_at >= '{start_utc}' AND downloaded_at <= '{end_utc}'")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: schedule={r[1]}, downloaded={r[2]}")
print()

# 8. OfflineSyncMetadata (synced_at in range)
print("8. OfflineSyncMetadata (synced_at in range):")
cursor.execute(f"SELECT id, synced_at FROM distribution_offlinesyncmetadata WHERE synced_at >= '{start_utc}' AND synced_at <= '{end_utc}'")
rows = cursor.fetchall()
print(f"   Count: {len(rows)}")
for r in rows:
    print(f"   ID {r[0]}: {r[1]}")
print()

print("=" * 60)
print("END OF DRY RUN")
print("=" * 60)

conn.close()
