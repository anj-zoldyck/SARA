from django import forms
# pyrefly: ignore [missing-import]
from .models import Household, Family, FamilyMember, SeniorCitizenProfile, SoloParentProfile, PWDProfile, SOLO_PARENT_CATEGORY_CHOICES

# ----------------- Household Form -----------------

ACCESS_CHOICES = (
    ('CONCRETE_ROAD', 'Concrete Road'),
    ('GRAVEL_ROAD', 'Gravel Road'),
    ('DIRT_ROAD', 'Dirt Road'),
    ('FOOT_TRAIL', 'Foot Trail'),
)

class HouseholdForm(forms.ModelForm):
    accessibility = forms.MultipleChoiceField(
        choices=ACCESS_CHOICES, 
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}), 
        required=False
    )

    class Meta:
        model = Household
        fields = [
            'house_number', 'land_use', 'hazard_exposure', 
            'flood_depth', 'flood_frequency', 'hazard_other_description', 'accessibility', 'location_notes'
        ]

        widgets = {
            'house_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'House Number'
            }),
            'land_use': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'hazard_exposure': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'flood_depth': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1 meter, knee-deep'}),
            'flood_frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Once a year, During typhoons'}),
            'hazard_other_description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Please specify the hazard'}),
            'location_notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Near the Barangay Hall'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.accessibility:
            self.initial['accessibility'] = self.instance.accessibility.split(',')

    def clean_accessibility(self):
        data = self.cleaned_data.get('accessibility', [])
        return ','.join(data)

# ----------------- Family Form -----------------
class FamilyForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ['family_name']

        widgets = {
            'family_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Family Name'
            }),
        }

# ----------------- Family Member Form -----------------
class FamilyMemberForm(forms.ModelForm):
    class Meta:
        model = FamilyMember
        fields = [
            'first_name', 'middle_name', 'last_name', 'suffix',
            'relationship', 'birthdate', 'birthplace', 'sex', 'civil_status',
            'philsys_card_no', 'religion', 'citizenship', 'occupation',
            'contact_number', 'email', 'educational_attainment', 'education_status',
            'monthly_income', 'is_pwd', 'is_solo_parent', 'is_senior_citizen', 'is_indigenous', 'is_out_of_school_youth', 'is_out_of_school_children', 'profile_image'
        ]

        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'suffix': forms.TextInput(attrs={'class': 'form-control'}),
            'relationship': forms.Select(attrs={'class': 'form-select'}),
            'birthdate': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'birthplace': forms.TextInput(attrs={'class': 'form-control'}),
            'sex': forms.Select(attrs={'class': 'form-select'}),
            'civil_status': forms.Select(attrs={'class': 'form-select'}),
            'philsys_card_no': forms.TextInput(attrs={'class': 'form-control'}),
            'religion': forms.TextInput(attrs={'class': 'form-control'}),
            'citizenship': forms.TextInput(attrs={'class': 'form-control'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '09...'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'monthly_income': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter 0 if unemployed, a student, or a minor with no income'}),
            'educational_attainment': forms.Select(attrs={'class': 'form-select', 'id': 'id_educational_attainment'}),
            'education_status': forms.Select(attrs={'class': 'form-select', 'id': 'id_education_status'}),
            'is_pwd': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_solo_parent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_senior_citizen': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_indigenous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_out_of_school_youth': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_out_of_school_children': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'profile_image': forms.FileInput(attrs={'class': 'd-none', 'id': 'profile_image_input', 'accept': 'image/*'}),
        }

# ----------------- Special Profile Forms -----------------

class SeniorCitizenProfileForm(forms.ModelForm):
    class Meta:
        model = SeniorCitizenProfile
        exclude = ['member', 'registered_at', 'registered_by']
        widgets = {
            'other_skills': forms.TextInput(attrs={'class': 'form-control'}),
            'ctc_no': forms.TextInput(attrs={'class': 'form-control'}),
        }

class SoloParentProfileForm(forms.ModelForm):
    class Meta:
        model = SoloParentProfile
        exclude = ['member', 'registered_at', 'registered_by']
        widgets = {
            'id_number': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(choices=SOLO_PARENT_CATEGORY_CHOICES, attrs={'class': 'form-select'}),
            'is_4ps_member': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_indigenous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_lgbtq': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_pwd': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_address': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_number': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_application': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

class PWDProfileForm(forms.ModelForm):
    class Meta:
        model = PWDProfile
        exclude = ['member', 'registered_at', 'registered_by']
        widgets = {
            'pwd_id_number': forms.TextInput(attrs={'class': 'form-control'}),
            'date_issued': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'disability_type': forms.Select(attrs={'class': 'form-select'}),
            'cause_of_disability': forms.Select(attrs={'class': 'form-select'}),
            'employment_status': forms.TextInput(attrs={'class': 'form-control'}),
            'certifying_physician': forms.TextInput(attrs={'class': 'form-control'}),
        }
