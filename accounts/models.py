from django.contrib.auth.models import AbstractUser
from django.db import models
import datetime
from django.core.validators import RegexValidator
from accounts.utils import user_profile_image_path

# ----------------- Custom User -----------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('MSWDO', 'MSWDO Admin'),
        ('MSWDO_STAFF', 'MSWDO Staff'),
        ('BARANGAY', 'Barangay Admin'),
    )

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    barangay = models.ForeignKey(
        'Barangay', on_delete=models.SET_NULL, blank=True, null=True, related_name='users'
    )
    is_active = models.BooleanField(default=True)
    
    # Optional Profile Fields
    middle_name = models.CharField(max_length=150, blank=True)
    suffix = models.CharField(max_length=10, blank=True, null=True)
    position = models.CharField(max_length=100, blank=True)
    
    SEX_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True)
    
    birthdate = models.DateField(blank=True, null=True)
    
    @property
    def age(self):
        """
        Dynamically calculate age from birthdate to avoid storing a stale value.
        Using a property ensures it always returns the correct age on-the-fly,
        requiring no cron jobs or scheduled updates.
        """
        if self.birthdate:
            today = datetime.date.today()
            return today.year - self.birthdate.year - ((today.month, today.day) < (self.birthdate.month, self.birthdate.day))
        return None

    contact_number = models.CharField(
        max_length=13, 
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^(09|\+639)\d{9}$',
                message="Phone number must be entered in the format: '09XXXXXXXXX' or '+639XXXXXXXXX'."
            )
        ]
    )
    
    profile_image = models.ImageField(upload_to=user_profile_image_path, blank=True, null=True)

# ----------------- Barangay Model -----------------
class Barangay(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
