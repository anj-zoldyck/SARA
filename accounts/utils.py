def user_profile_image_path(instance, filename):
    role_folder_map = {
        'MSWDO': 'MSWDO Admin',
        'MSWDO_STAFF': 'MSWDO Staff',
    }
    
    # Barangay Admin folder needs to handle missing barangay gracefully
    if instance.role == 'BARANGAY':
        barangay_name = instance.barangay.name if instance.barangay else "Unassigned"
        role_folder = f'Barangay Admin/{barangay_name}'
    else:
        role_folder = role_folder_map.get(instance.role, 'Unknown')
        
    return f'userprofile/{role_folder}/{instance.username}/{filename}'

def resident_profile_image_path(instance, filename):
    """
    Scaffolding for future Resident profiling images.
    Upload path: userprofile/Residents/<barangay_name>/<zone_name>/<family_name>/image.png
    """
    barangay_name = instance.family.household.barangay.name if instance.family and instance.family.household and instance.family.household.barangay else "UnknownBarangay"
    zone_name = instance.family.household.zone.name if instance.family and instance.family.household and instance.family.household.zone else "UnknownZone"
    family_name = instance.family.family_name if instance.family else "UnknownFamily"
    
    return f'userprofile/Residents/{barangay_name}/{zone_name}/{family_name}/{filename}'
