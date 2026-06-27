from django.db import models

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
    requires_pwd = models.BooleanField(default=False)
    requires_solo_parent = models.BooleanField(default=False)

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
