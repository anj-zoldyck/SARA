from django.db import models
from django.conf import settings
from accounts.models import Barangay
from households.models import Family, FamilyMember
from programs.models import Assistance

# ----------------- AidClaim Model -----------------
class AidClaim(models.Model):
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    family_member = models.ForeignKey(
        FamilyMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Required for individual-based assistance"
    )
       
    assistance = models.ForeignKey(
        Assistance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='claims'
    )
    schedule = models.ForeignKey('AidSchedule', on_delete=models.CASCADE, null=True)
    claimed_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
            settings.AUTH_USER_MODEL,
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
        Assistance,
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
