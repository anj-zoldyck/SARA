from django.db import models
from accounts.models import Barangay

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
