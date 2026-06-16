from django.contrib.auth.models import AbstractUser
from django.db import models
from django.shortcuts import render

# ----------------- Custom User -----------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('MSWDO', 'MSWDO Admin'),
        ('BARANGAY', 'Barangay Admin'),
    )

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    barangay = models.ForeignKey(
        'Barangay', on_delete=models.SET_NULL, blank=True, null=True, related_name='users'
    )
    is_active = models.BooleanField(default=True)

# ----------------- Barangay Model -----------------
class Barangay(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

# ----------------- Zone Model -----------------
class Zone(models.Model):
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='zones')
    name = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.barangay.name} - {self.name}"

# ----------------- Household Model -----------------
class Household(models.Model):
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='households')
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='households')
    house_number = models.CharField(max_length=50)
    family_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.family_name} ({self.barangay.name} - {self.zone.name})"
    
    @property
    def address(self):
        return f"{self.house_number}, {self.zone.name}, {self.barangay.name}"

# ----------------- Family Model -----------------
class Family(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='families')
    family_name = models.CharField(max_length=100)

    rfid_uid = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.family_name} ({self.household})"

# ----------------- FamilyMember Model -----------------
class FamilyMember(models.Model):
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name='members'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    relationship = models.CharField(max_length=50)
    age = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

# =============================================================
# NEW DYNAMIC AID STRUCTURE (replaces hardcoded AidType)
# =============================================================

# ----------------- Program Model -----------------
class Program(models.Model):
    """
    Top-level aid program managed by MSWDO.
    Examples: AICS, AKAP, Disaster Relief
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


# ----------------- AidCategory Model -----------------
class AidCategory(models.Model):
    """
    A specific type of aid under a Program.
    Examples: under AICS → Medical, Burial, Food, Transportation, Financial
    """
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name='aid_categories'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.program.name} — {self.name}"

    class Meta:
        ordering = ['name']
        unique_together = ('program', 'name')


# ----------------- Assistance Model -----------------
class Assistance(models.Model):
    """
    A claimable assistance item.
    Combines a Program + AidCategory + who can claim it.
    This is what gets attached to an AidSchedule.

    Example rows:
      AICS + Medical      + individual
      AICS + Burial       + family
      Disaster Relief + Food Packs + family
    """
    BENEFICIARY_TYPE = [
        ('individual', 'Individual'),
        ('family', 'Family'),
    ]

    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name='assistances'
    )
    aid_category = models.ForeignKey(
        AidCategory,
        on_delete=models.CASCADE,
        related_name='assistances'
    )
    beneficiary_type = models.CharField(
        max_length=20,
        choices=BENEFICIARY_TYPE,
        default='family'
    )

    # For individual-based: optional minimum age filter
    # e.g. Senior = 60, PWD = None, Solo Parent = None
    minimum_age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank if no age requirement."
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.program.name} › {self.aid_category.name} ({self.get_beneficiary_type_display()})"

    class Meta:
        ordering = ['program', 'aid_category']
        unique_together = ('program', 'aid_category', 'beneficiary_type')

    @property
    def is_individual(self):
        return self.beneficiary_type == 'individual'

    @property
    def is_family(self):
        return self.beneficiary_type == 'family'

# ----------------- AidClaim Model -----------------
class AidClaim(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    family_member = models.ForeignKey(
        'FamilyMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Required for individual-based assistance"
    )
       
        # NEW - replaces aid_type
    assistance = models.ForeignKey(
        'Assistance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='claims'
    )
    schedule = models.ForeignKey('AidSchedule', on_delete=models.CASCADE, null=True)
    claimed_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
            User,
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name='processed_claims'
        )

    def __str__(self):
        label = str(self.assistance) if self.assistance else 'No Assistance'
        if self.family_member:
            return f"{self.family_member} ({self.family}) — {label} — {self.claimed_at}"
        return f"{self.family} — {label} — {self.claimed_at}"

# ----------------- AidSchedule Model -----------------
class AidSchedule(models.Model):

    assistance = models.ForeignKey(
        'Assistance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules'
    )
    
    schedule_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    location = models.CharField(max_length=255)

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.assistance:
            return f"{self.assistance} @ {self.schedule_datetime}"
        return f"{self.assistance} @ {self.schedule_datetime}"


