from django import forms
from .models import Household, Family, FamilyMember

# ----------------- Household Form -----------------
class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ['house_number', 'family_name']

        widgets = {
            'house_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'House Number'
            }),
            'family_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Family Name'
            }),
        }

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
            'first_name', 'last_name', 'relationship', 'birthdate',
            'is_pwd', 'is_solo_parent', 'is_senior_citizen', 'profile_image'
        ]

        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'birthdate': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_pwd': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_solo_parent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_senior_citizen': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'profile_image': forms.FileInput(attrs={'class': 'd-none', 'id': 'profile_image_input', 'accept': 'image/*'}),
        }
