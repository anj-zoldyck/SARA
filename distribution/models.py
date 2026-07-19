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
    CLAIM_TYPE_CHOICES = (
        ('DISTRIBUTION', 'Distribution Event'),
        ('WALK_IN', 'Walk-in / Office Visit'),
    )
    claim_type = models.CharField(
        max_length=20,
        choices=CLAIM_TYPE_CHOICES,
        default='DISTRIBUTION'
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
    
    # Using DecimalField instead of FloatField is essential for financial data to prevent
    # floating-point rounding drift. It guarantees exact decimal arithmetic, which is 
    # critical when calculating slot counts (budget / per_beneficiary_amount).
    # Consistent with FamilyMember.monthly_income pattern in this codebase.
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    per_beneficiary_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    schedule_datetime = models.DateTimeField()

    is_finished = models.BooleanField(default=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    finished_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    # finish_reason exists to distinguish "everyone got served" from "staff had to force-close with no-shows remaining"
    # — useful for future reporting.
    finish_reason = models.CharField(
        max_length=20,
        choices=(('COMPLETED', 'All Beneficiaries Claimed'), ('FORCED', 'Manually Ended (Incomplete)')),
        blank=True
    )

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

# ----------------- Beneficiary List Models -----------------
# The beneficiary list is saved persistently to enable future report generation, and to explicitly 
# restrict RFID scanning to only listed beneficiaries during the actual distribution event. 
# This lock-in ensures budget compliance.

class GeneratedBeneficiaryList(models.Model):
    schedule = models.OneToOneField('AidSchedule', on_delete=models.CASCADE, related_name='beneficiary_list')
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    prioritization_strategy_used = models.CharField(max_length=30)  # snapshot at generation time

class GeneratedBeneficiary(models.Model):
    beneficiary_list = models.ForeignKey(GeneratedBeneficiaryList, on_delete=models.CASCADE, related_name='entries')
    household = models.ForeignKey('households.Household', on_delete=models.CASCADE, null=True, blank=True)
    family = models.ForeignKey('households.Family', on_delete=models.CASCADE, null=True, blank=True)
    # Exactly one of household/family should be set, depending on assistance.beneficiary_type —
    # This mirrors the existing Household vs Family beneficiary_type distinction already used elsewhere
    # in this system (e.g. AidClaim.family_member being optional).
    added_manually = models.BooleanField(default=False)  # True if added via manual override, not auto-generated
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    @property
    def display_name(self):
        if self.family:
            return f"{self.family.family_name} Family"
        elif self.household:
            first_family = self.household.families.first()
            if first_family:
                head = first_family.head_member
                if head:
                    return f"{head.first_name} {head.last_name}"
                first_member = first_family.members.first()
                if first_member:
                    return f"{first_member.first_name} {first_member.last_name}"
            return f"{self.household.address} (No members registered)"
        return "Unknown Beneficiary"

# ----------------- AssignedTo Model -----------------
# This model handles staff assignments for distribution schedules.
class AssignedTo(models.Model):
    schedule = models.ForeignKey('AidSchedule', on_delete=models.CASCADE, related_name='assignments')
    
    # Note: staff must have the MSWDO_STAFF role. We do not enforce this at the model
    # level (e.g. via limit_choices_to={'role': 'MSWDO_STAFF'}) because model-level
    # constraints can sometimes break if a user's role changes historically, and it's
    # cleaner to validate this strictly in the form/view layer when creating assignments.
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='distribution_assignments')
    
    barangay = models.ForeignKey('accounts.Barangay', on_delete=models.CASCADE)
    
    # Zone is optional to allow for flexible assignments:
    # - If zone is set, the staff is assigned strictly to that specific zone within the barangay.
    # - If zone is blank (None), it acts as a "barangay-wide" assignment, meaning the staff
    #   can process claims for ANY household within that barangay.
    zone = models.ForeignKey('households.Zone', on_delete=models.CASCADE, null=True, blank=True,
                              help_text="Optional — leave blank if staff is assigned to the whole barangay, not a specific zone.")
    
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        # A staff member shouldn't be assigned to the exact same schedule+barangay+zone combo twice
        unique_together = ('schedule', 'staff', 'barangay', 'zone')
