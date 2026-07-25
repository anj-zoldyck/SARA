from PIL import Image
from django.core.exceptions import ValidationError

MAX_IMAGE_SIZE_MB = 5
ALLOWED_IMAGE_FORMATS = ('JPEG', 'PNG', 'GIF', 'WEBP')


def validate_image_file(file):
    """
    Validates an uploaded file is genuinely an image, not just named like one.
    - Checks file size against MAX_IMAGE_SIZE_MB.
    - Uses Pillow to actually open and verify the file's content is a real,
      readable image (not a renamed executable, script, or corrupted file
      pretending to be an image via its extension alone).
    - Checks the image format is in the allowed list, since Pillow can open
      formats we may not want to accept.

    Why this matters: relying on file extension or the browser's `accept` 
    attribute alone is trivial to bypass (e.g., renaming malicious.exe to
    photo.jpg still passes those checks) — Pillow actually attempts to
    decode the file as image data, which a non-image file will fail.
    """
    # Size check
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"Image file too large. Maximum size is {MAX_IMAGE_SIZE_MB}MB.")

    # Content verification via Pillow
    try:
        img = Image.open(file)
        img.verify()  # Verifies file integrity without fully loading pixel data
    except Exception:
        raise ValidationError("The uploaded file is not a valid image.")

    # Re-open after verify() since verify() can leave the file object in a
    # state that prevents further reading — this is a documented Pillow
    # behavior: verify() reads the file but doesn't close it properly, leaving
    # the file pointer at the end. We must seek(0) to reset the pointer before
    # reopening, otherwise Image.open() will fail or read nothing.
    file.seek(0)
    img = Image.open(file)
    if img.format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(f"Unsupported image format: {img.format}. Allowed: {', '.join(ALLOWED_IMAGE_FORMATS)}.")

    file.seek(0)  # Reset file pointer so Django can still save it normally afterward


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
