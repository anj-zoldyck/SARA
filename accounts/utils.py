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
    family = instance.family
    household = family.household
    zone = household.zone
    barangay = zone.barangay
    member_name = f"{instance.first_name} {instance.last_name}"
    return (
        f"userprofile/Residents/{barangay.name}/{zone.name}/"
        f"{household.house_number}/{family.family_name}/{member_name}/{filename}"
    )
