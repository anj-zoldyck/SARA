import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# UTC range: Sep 6 00:00 PHT = Sep 5 16:00 UTC, Sep 13 23:59:59 PHT = Sep 13 15:59:59 UTC
start_utc = '2026-09-05 16:00:00'
end_utc = '2026-09-13 15:59:59'

print("=" * 80)
print("DELETING TEST DATA (Sep 6-13, 2026 PH time)")
print("=" * 80)
print(f"UTC Range: {start_utc} to {end_utc}")
print()

# Delete in reverse dependency order

# 1. Delete GeneratedBeneficiary (via schedule FK)
print("1. Deleting GeneratedBeneficiary...")
cursor.execute(f"""
    DELETE FROM distribution_generatedbeneficiary
    WHERE beneficiary_list_id IN (
        SELECT id FROM distribution_generatedbeneficiarylist
        WHERE schedule_id IN (
            SELECT id FROM distribution_aidschedule
            WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'
        )
    )
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

# 2. Delete GeneratedBeneficiaryList (via schedule FK)
print("2. Deleting GeneratedBeneficiaryList...")
cursor.execute(f"""
    DELETE FROM distribution_generatedbeneficiarylist
    WHERE schedule_id IN (
        SELECT id FROM distribution_aidschedule
        WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'
    )
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

# 3. Delete AssignedTo (via schedule FK)
print("3. Deleting AssignedTo...")
cursor.execute(f"""
    DELETE FROM distribution_assignedto
    WHERE schedule_id IN (
        SELECT id FROM distribution_aidschedule
        WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'
    )
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

# 4. Delete BeneficiaryBackupDownload (downloaded_at in range)
print("4. Deleting BeneficiaryBackupDownload...")
cursor.execute(f"""
    DELETE FROM distribution_beneficiarybackupdownload
    WHERE downloaded_at >= '{start_utc}' AND downloaded_at <= '{end_utc}'
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

# 5. Delete AidClaim (claimed_at in range)
print("5. Deleting AidClaim...")
cursor.execute(f"""
    DELETE FROM distribution_aidclaim
    WHERE claimed_at >= '{start_utc}' AND claimed_at <= '{end_utc}'
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

# 6. Delete AidSchedule (schedule_datetime in range)
print("6. Deleting AidSchedule...")
cursor.execute(f"""
    DELETE FROM distribution_aidschedule
    WHERE schedule_datetime >= '{start_utc}' AND schedule_datetime <= '{end_utc}'
""")
print(f"   Deleted: {cursor.rowcount} rows")
conn.commit()

print()
print("=" * 80)
print("DELETION COMPLETE")
print("=" * 80)

conn.close()
