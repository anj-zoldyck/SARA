from django.db import models
from accounts.models import Barangay
from accounts.utils import resident_profile_image_path
import datetime
from django.core.validators import RegexValidator

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
    LAND_USE_CHOICES = (
        ('RESIDENTIAL', 'Residential'),
        ('AGRICULTURAL', 'Agricultural'),
        ('COMMERCIAL', 'Commercial'),
        ('INDUSTRIAL', 'Industrial'),
        ('INSTITUTIONAL', 'Institutional'),
        ('FISHING', 'Fishing'),
    )

    HAZARD_CHOICES = (
        ('NONE', 'No Hazard'),
        ('FLOOD', 'Flood'),
        ('LANDSLIDE', 'Landslide'),
        ('FIRE', 'Fire'),
        ('EARTHQUAKE', 'Earthquake/Fault'),
        ('RIVERBANK_EROSION', 'Riverbank Erosion'),
        ('OTHER', 'Other'),
    )

    house_number = models.CharField(max_length=50)
    land_use = models.CharField(max_length=20, choices=LAND_USE_CHOICES)
    hazard_exposure = models.CharField(max_length=20, choices=HAZARD_CHOICES)
    flood_depth = models.CharField(max_length=50, blank=True)
    flood_frequency = models.CharField(max_length=50, blank=True)
    hazard_other_description = models.CharField(max_length=255, blank=True)
    accessibility = models.CharField(max_length=255, blank=True)
    location_notes = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return f"House {self.house_number} ({self.barangay.name} - {self.zone.name})"
    
    @property
    def address(self):
        return f"{self.house_number}, {self.zone.name}, {self.barangay.name}"

    @property
    def accessibility_labels(self):
        if not self.accessibility:
            return []
        choices = {
            'CONCRETE_ROAD': 'Concrete Road',
            'GRAVEL_ROAD': 'Gravel Road',
            'DIRT_ROAD': 'Dirt Road',
            'FOOT_TRAIL': 'Foot Trail',
        }
        return [choices.get(val.strip(), val.strip()) for val in self.accessibility.split(',')]

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

    @property
    def head_member(self):
        return self.members.filter(relationship='HEAD').first()

# ----------------- FamilyMember Model -----------------
RELATIONSHIP_CHOICES = (
    ('HEAD', 'Head of Family'),
    ('SPOUSE', 'Spouse'),
    ('SON', 'Son'),
    ('DAUGHTER', 'Daughter'),
    ('FATHER', 'Father'),
    ('MOTHER', 'Mother'),
    ('SON_IN_LAW', 'Son-in-Law'),
    ('DAUGHTER_IN_LAW', 'Daughter-in-Law'),
    ('FATHER_IN_LAW', 'Father-in-Law'),
    ('MOTHER_IN_LAW', 'Mother-in-Law'),
    ('GRANDCHILD', 'Grandchild'),
    ('SIBLING', 'Sibling/Brother/Sister'),
    ('GRANDPARENT', 'Grandparent'),
    ('OTHER_RELATIVE', 'Other Relative'),
    ('NON_RELATIVE', 'Non-Relative/Boarder'),
)

EDUCATIONAL_ATTAINMENT_CHOICES = (
    ('Elementary', 'Elementary'),
    ('High School', 'High School'),
    ('College', 'College'),
    ('Post Grad', 'Post Grad'),
    ('Vocational', 'Vocational'),
)

EDUCATION_STATUS_CHOICES = (
    ('Graduate', 'Graduate'),
    ('Under Graduate', 'Under Graduate'),
)

CIVIL_STATUS_CHOICES = (
    ('Single', 'Single'),
    ('Married', 'Married'),
    ('Widowed', 'Widowed'),
    ('Separated', 'Separated'),
    ('Annulled', 'Annulled'),
    ('Live-in', 'Live-in'),
)

SEX_CHOICES = (
    ('M', 'Male'),
    ('F', 'Female'),
)

class FamilyMember(models.Model):
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name='members'
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True, null=True)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES)
    birthdate = models.DateField(null=True, blank=True)
    birthplace = models.CharField(max_length=150, blank=True, null=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True, null=True)
    civil_status = models.CharField(max_length=50, choices=CIVIL_STATUS_CHOICES, blank=True, null=True)
    philsys_card_no = models.CharField(max_length=50, blank=True, null=True)
    religion = models.CharField(max_length=100, blank=True, null=True)
    citizenship = models.CharField(max_length=50, default='Filipino', blank=True, null=True)
    occupation = models.CharField(max_length=150, blank=True, null=True)
    contact_number = models.CharField(
        max_length=13, 
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^(09|\+639)\d{9}$',
                message="Phone number must be entered in the format: '09XXXXXXXXX' or '+639XXXXXXXXX'."
            )
        ]
    )
    email = models.EmailField(blank=True, null=True)
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    educational_attainment = models.CharField(max_length=50, choices=EDUCATIONAL_ATTAINMENT_CHOICES, blank=True, null=True)
    education_status = models.CharField(max_length=50, choices=EDUCATION_STATUS_CHOICES, blank=True, null=True)
    
    is_pwd = models.BooleanField(default=False)
    is_solo_parent = models.BooleanField(default=False)
    is_senior_citizen = models.BooleanField(default=False)
    is_indigenous = models.BooleanField(default=False)
    is_out_of_school_youth = models.BooleanField(default=False)
    is_out_of_school_children = models.BooleanField(default=False)
    profile_image = models.ImageField(upload_to=resident_profile_image_path, blank=True, null=True)

    @property
    def age(self):
        if self.birthdate:
            today = datetime.date.today()
            return today.year - self.birthdate.year - ((today.month, today.day) < (self.birthdate.month, self.birthdate.day))
        return None

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

# ----------------- Special Profiles -----------------

class SeniorCitizenProfile(models.Model):
    member = models.OneToOneField(FamilyMember, on_delete=models.CASCADE, related_name='senior_profile')
    other_skills = models.CharField(max_length=100, blank=True, null=True)
    ctc_no = models.CharField(max_length=50, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f"Senior Citizen Profile - {self.member}"

SOLO_PARENT_CATEGORY_CHOICES = (
    ('A1', 'Birth of a child as a consequence of rape'),
    ('A2', 'Widow/widower'),
    ('A3', 'Spouse of person deprived of liberty (PDL)'),
    ('A4', 'Spouse of person with disability (PWD)'),
    ('A5', 'Due to de facto separation'),
    ('A6', 'Due to nullity of marriage'),
    ('A7', 'Abandoned'),
    ('B1', 'Spouse of the OFW'),
    ('B2', 'Relative of the OFW'),
    ('C', 'Unmarried Person'),
    ('D', 'Legal guardian'),
    ('E', 'Relative'),
    ('F', 'Pregnant Woman'),
)

class SoloParentProfile(models.Model):
    member = models.OneToOneField(FamilyMember, on_delete=models.CASCADE, related_name='solo_parent_profile')
    id_number = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=10, choices=SOLO_PARENT_CATEGORY_CHOICES, blank=True, null=True)
    is_4ps_member = models.BooleanField(default=False)
    is_indigenous = models.BooleanField(default=False)
    is_lgbtq = models.BooleanField(default=False)
    is_pwd = models.BooleanField(default=False)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_address = models.CharField(max_length=255, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=50, blank=True, null=True)
    date_of_application = models.DateField(blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f"Solo Parent Profile - {self.member}"

DISABILITY_TYPE_CHOICES = (
    ('Visual', 'Visual'),
    ('Hearing', 'Hearing'),
    ('Speech', 'Speech'),
    ('Orthopedic', 'Orthopedic'),
    ('Mental/Intellectual', 'Mental/Intellectual'),
    ('Psychosocial', 'Psychosocial'),
    ('Learning', 'Learning'),
    ('Chronic Illness/Rare Disease', 'Chronic Illness/Rare Disease'),
)

CAUSE_OF_DISABILITY_CHOICES = (
    ('Congenital', 'Congenital'),
    ('Acquired-Illness', 'Acquired-Illness'),
    ('Acquired-Injury', 'Acquired-Injury'),
    ('Acquired-Workplace', 'Acquired-Workplace'),
    ('Other', 'Other'),
)

class PWDProfile(models.Model):
    member = models.OneToOneField(FamilyMember, on_delete=models.CASCADE, related_name='pwd_profile')
    pwd_id_number = models.CharField(max_length=50, blank=True, null=True)
    date_issued = models.DateField(blank=True, null=True)
    disability_type = models.CharField(max_length=50, choices=DISABILITY_TYPE_CHOICES, blank=True, null=True)
    cause_of_disability = models.CharField(max_length=50, choices=CAUSE_OF_DISABILITY_CHOICES, blank=True, null=True)
    employment_status = models.CharField(max_length=50, blank=True, null=True)
    certifying_physician = models.CharField(max_length=100, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f"PWD Profile - {self.member}"
