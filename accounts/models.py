from django.contrib.auth.models import AbstractUser
from django.db import models

# ----------------- Custom User -----------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('MSWDO', 'MSWDO Admin'),
        ('BARANGAY', 'Barangay Admin'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    barangay = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

# ----------------- Zone Model -----------------
class Zone(models.Model):
    barangay = models.CharField(max_length=100)
    name = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.barangay} - {self.name}"

# ----------------- Household Model -----------------
class Household(models.Model):
    barangay = models.CharField(max_length=100)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='households')
    house_number = models.CharField(max_length=50)
    family_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.family_name} ({self.barangay} - {self.zone.name})"
    
# ----------------- Family Model -----------------
class Family(models.Model):
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='families'
    )
    family_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.family_name} - House {self.household.house_number}"
    
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


