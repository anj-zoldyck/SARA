from django.db import models
from programs.eligibility import get_eligibility_badges

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

    AID_TYPE_CHOICES = (
        ('CASH', 'Cash Assistance'),
        ('GOODS', 'Goods-in-Kind (rice, noodles, canned goods, etc.)'),
    )

    PRIORITIZATION_CHOICES = (
        ('LOWEST_INCOME_FIRST', 'Lowest Income First'),
        ('TYPHOON_PRIORITY', 'Typhoon/Vulnerability Priority'),
        ('RANDOM', 'Random Among Eligible'),
    )

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
    prioritization_strategy = models.CharField(
        max_length=30, choices=PRIORITIZATION_CHOICES, default='LOWEST_INCOME_FIRST',
        help_text="How to rank eligible beneficiaries when there are more eligible than available slots."
    )
    aid_type = models.CharField(
        max_length=10, choices=AID_TYPE_CHOICES, default='CASH',
        help_text="Used by the Rotation Eligibility rule to alternate beneficiaries between cash and goods-based aid across distribution cycles."
    )

    # For individual-based: optional minimum age filter
    # e.g. Senior = 60, PWD = None, Solo Parent = None
    minimum_age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank if no age requirement."
    )
    requires_pwd = models.BooleanField(default=False)
    requires_solo_parent = models.BooleanField(default=False)
    requires_senior_citizen = models.BooleanField(default=False)

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

    @property
    def eligibility_badges(self):
        return get_eligibility_badges(self)


# Expected config shapes per rule_type:
# INCOME_THRESHOLD: {"max_income": 15000}
# HOUSEHOLD_SIZE_INCOME: {"min_members": 5, "max_income": 20000}
# FLOOD_PRONE: {} (no config needed — checks Household.hazard_exposure == 'FLOOD'
#              OR household's zone has any FloodProneArea records)
# SPECIAL_CATEGORY: {"flags": ["is_pwd", "is_senior_citizen"]} — member must have
#                    AT LEAST ONE of the listed flags set to True (OR logic within
#                    this rule; this rule combines with AND against all other
#                    active rules on the same Assistance)
# DAYS_SINCE_LAST_ASSISTANCE: {"min_days": 30} — household/family must NOT have
#   received ANY AidClaim within the last `min_days` days to be eligible.
#   This checks claims across ALL assistances/programs, not just this one —
#   confirmed with the developer this is intentional (a general cooldown,
#   not per-program).
# ROTATION_ELIGIBILITY: {} (no config needed) — checks this household/family's
#   MOST RECENT AidClaim's assistance.aid_type. If their last claim was CASH,
#   they are only eligible for assistances with aid_type=GOODS this cycle,
#   and vice versa. If they have no prior claims at all, this rule passes
#   automatically (nothing to rotate away from yet).
# ACTIVE_TYPHOON_SIGNAL: {"min_signal": 1} — checks the latest WeatherSnapshot
#   and confirms get_tcws_signal(current_wind_speed) >= min_signal. If no
#   signal is currently active (or no WeatherSnapshot exists), this rule fails
#   (assistance is not currently active/needed).
class EligibilityRule(models.Model):
    RULE_TYPE_CHOICES = (
        ('INCOME_THRESHOLD', 'Income Threshold'),
        ('HOUSEHOLD_SIZE_INCOME', 'Household Size + Income Combination'),
        ('FLOOD_PRONE', 'Flood-Prone Status'),
        ('SPECIAL_CATEGORY', 'Special Category Membership'),
        ('DAYS_SINCE_LAST_ASSISTANCE', 'Days Since Last Assistance'),
        ('ROTATION_ELIGIBILITY', 'Rotation Eligibility (Cash/Goods Alternation)'),
        ('ACTIVE_TYPHOON_SIGNAL', 'Active Typhoon Signal'),
    )
    assistance = models.ForeignKey('Assistance', on_delete=models.CASCADE, related_name='eligibility_rules')
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES)
    # Generic config storage: each rule_type interprets this differently.
    # Using JSONField keeps this model reusable across very different rule shapes
    # (a threshold rule needs one number; a category rule needs a list of flags)
    # without needing a separate table per rule type.
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.assistance} — {self.get_rule_type_display()}"
