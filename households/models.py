from django.db import models
from accounts.models import Barangay
from accounts.utils import resident_profile_image_path
import datetime
from django.core.validators import RegexValidator
from django.conf import settings

# ----------------- Zone Model -----------------
class Zone(models.Model):
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='zones')
    name = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.barangay.name} - {self.name}"

class FloodProneArea(models.Model):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='flood_prone_areas')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

GOVERNMENT_ID_CHOICES = (
    ('PHILSYS', 'PhilSys Card'),
    ('PASSPORT', 'Philippine Passport'),
    ('DRIVERS_LICENSE', "Driver's License"),
    ('PHILHEALTH', 'PhilHealth ID'),
    ('UMID', 'UMID'),
    ('SSS', 'SSS ID'),
    ('POSTAL', 'Philippine Postal ID'),
    ('PRC', 'PRC ID'),
    ('VOTERS', "Voter's ID"),
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
    government_id_type = models.CharField(
        max_length=20, choices=GOVERNMENT_ID_CHOICES,
        blank=True, default='PHILSYS'
    )
    government_id_number = models.CharField(max_length=50, blank=True, null=True)
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
    senior_citizen_id_number = models.CharField(max_length=50, blank=True, null=True)
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

APPLICATION_TYPE_CHOICES = (
    ('NEW', 'New Applicant'),
    ('RENEWAL', 'Renewal'),
)

DISABILITY_TYPE_CHOICES = (
    ('DEAF_HARD_OF_HEARING', 'Deaf or Hard of Hearing'),
    ('INTELLECTUAL', 'Intellectual Disability'),
    ('LEARNING', 'Learning Disability'),
    ('MENTAL', 'Mental Disability'),
    ('PHYSICAL_ORTHOPEDIC', 'Physical Disability (Orthopedic)'),
    ('PSYCHOSOCIAL', 'Psychosocial Disability'),
    ('SPEECH_LANGUAGE', 'Speech and Language Impairment'),
    ('VISUAL', 'Visual Disability'),
    ('CANCER', 'Cancer (RA11215)'),
    ('RARE_DISEASE', 'Rare Disease (RA10747)'),
)

CAUSE_OF_DISABILITY_CHOICES = (
    ('Congenital / Inborn', (
        ('CONGENITAL_AUTISM', 'Autism'),
        ('CONGENITAL_ADHD', 'ADHD'),
        ('CONGENITAL_CEREBRAL_PALSY', 'Cerebral Palsy'),
        ('CONGENITAL_DOWN_SYNDROME', 'Down Syndrome'),
    )),
    ('Acquired', (
        ('ACQUIRED_CHRONIC_ILLNESS', 'Chronic Illness'),
        ('ACQUIRED_CEREBRAL_PALSY', 'Cerebral Palsy'),
        ('ACQUIRED_INJURY', 'Injury'),
    )),
)

EMPLOYMENT_STATUS_CHOICES = (
    ('EMPLOYED', 'Employed'),
    ('UNEMPLOYED', 'Unemployed'),
    ('SELF_EMPLOYED', 'Self-employed'),
)

EMPLOYMENT_TYPE_CHOICES = (
    ('PERMANENT', 'Permanent / Regular'),
    ('SEASONAL', 'Seasonal'),
    ('CASUAL', 'Casual'),
    ('EMERGENCY', 'Emergency'),
)

EMPLOYMENT_CATEGORY_CHOICES = (
    ('GOVERNMENT', 'Government'),
    ('PRIVATE', 'Private'),
)

ACCOMPLISHED_BY_CHOICES = (
    ('APPLICANT', 'Applicant'),
    ('GUARDIAN', 'Guardian'),
    ('REPRESENTATIVE', 'Representative'),
)

class PWDProfile(models.Model):
    member = models.OneToOneField(FamilyMember, on_delete=models.CASCADE, related_name='pwd_profile')

    # Field 1 — Application Type
    application_type = models.CharField(max_length=10, choices=APPLICATION_TYPE_CHOICES, blank=True)

    # Field 2 — PWD ID Number (format: RR-PPMM-BBB-NNNNNNN)
    pwd_id_number = models.CharField(max_length=50, blank=True, null=True)

    # Field 3 — Date Applied (renamed from date_issued)
    date_applied = models.DateField(blank=True, null=True)

    # Field 8 — Type of Disability
    disability_type = models.CharField(max_length=50, choices=DISABILITY_TYPE_CHOICES, blank=True)

    # Field 9 — Cause of Disability
    cause_of_disability = models.CharField(max_length=50, choices=CAUSE_OF_DISABILITY_CHOICES, blank=True)

    # Field 13 — Employment Details
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True)
    employment_category = models.CharField(max_length=20, choices=EMPLOYMENT_CATEGORY_CHOICES, blank=True)

    # Field 15 — Organization Information
    organization_affiliated = models.CharField(max_length=200, blank=True)
    organization_contact_person = models.CharField(max_length=200, blank=True)
    organization_office_address = models.CharField(max_length=255, blank=True)
    organization_tel_no = models.CharField(max_length=50, blank=True)

    # Field 16 — Government ID Reference Numbers
    sss_no = models.CharField(max_length=50, blank=True)
    gsis_no = models.CharField(max_length=50, blank=True)
    pagibig_no = models.CharField(max_length=50, blank=True)
    psn_no = models.CharField(max_length=50, blank=True)
    philhealth_no = models.CharField(max_length=50, blank=True)

    # Field 17 — Family Background
    father_last_name = models.CharField(max_length=100, blank=True)
    father_first_name = models.CharField(max_length=100, blank=True)
    father_middle_name = models.CharField(max_length=100, blank=True)
    mother_last_name = models.CharField(max_length=100, blank=True)
    mother_first_name = models.CharField(max_length=100, blank=True)
    mother_middle_name = models.CharField(max_length=100, blank=True)
    guardian_last_name = models.CharField(max_length=100, blank=True)
    guardian_first_name = models.CharField(max_length=100, blank=True)
    guardian_middle_name = models.CharField(max_length=100, blank=True)

    # Field 18 — Accomplished By
    accomplished_by = models.CharField(max_length=20, choices=ACCOMPLISHED_BY_CHOICES, blank=True)

    # Field 19 — Certifying Physician
    certifying_physician = models.CharField(max_length=200, blank=True)
    physician_license_no = models.CharField(max_length=50, blank=True)

    # Audit fields
    registered_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )

    def __str__(self):
        return f"PWD Profile - {self.member}"

# ----------------- Weather Model -----------------

class WeatherSnapshot(models.Model):
    fetched_at = models.DateTimeField(auto_now_add=True)
    current_wind_speed_kmh = models.DecimalField(max_digits=6, decimal_places=2)
    current_precipitation_mm = models.DecimalField(max_digits=6, decimal_places=2)
    forecast_data = models.JSONField()  # store the full hourly forecast array for reference
    fetch_successful = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Weather Snapshot - {self.fetched_at.strftime('%Y-%m-%d %H:%M:%S')} - Success: {self.fetch_successful}"
