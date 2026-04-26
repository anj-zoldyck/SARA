from django import forms
from .models import Household, Family, FamilyMember, User, Barangay

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
        fields = ['first_name', 'last_name', 'relationship', 'age']

        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# ----------------- Barangay User Creation Form -----------------
class BarangayAdminForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'password', 'barangay']

    # Show barangay as dropdown
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.all(),
        empty_label="Select Barangay",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
