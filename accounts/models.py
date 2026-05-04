from django.contrib.auth.models import AbstractUser
from django.db import models
from django.shortcuts import render

# ----------------- Custom User -----------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('MSWDO', 'MSWDO Admin'),
        ('BARANGAY', 'Barangay Admin'),
    )

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

# ----------------- AidClaim Model -----------------
class AidType(models.TextChoices):
    RELIEF = 'RELIEF', 'Relief'
    SENIOR = 'SENIOR', 'Senior Citizen'
    # add more as needed

# ----------------- AidClaim Model -----------------
class AidClaim(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    family_member = models.ForeignKey(
        'FamilyMember',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="For individual aids like Senior"
    )
    aid_type = models.CharField(max_length=20, choices=AidType.choices)
    schedule = models.ForeignKey('AidSchedule', on_delete=models.CASCADE, null=True)
    claimed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.family_member:
            return f"{self.family_member} ({self.family}) - {self.aid_type} - {self.claimed_at}"
        return f"{self.family} - {self.aid_type} - {self.claimed_at}"

# ----------------- AidSchedule Model -----------------
class AidSchedule(models.Model):
    aid_type = models.CharField(max_length=20, choices=AidType.choices)

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
        return f"{self.aid_type} @ {self.schedule_datetime}"


