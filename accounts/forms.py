from django import forms
from .models import Household, Family, FamilyMember, User, Barangay, Program, AidCategory, Assistance

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
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

# ----------------- Barangay User Edit Form -----------------
class BarangayAdminEditForm(forms.ModelForm):
    """
    Edit form for an existing barangay account.
    Password is optional — leave blank to keep the current password.
    """
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Leave blank to keep current password'}),
        label='New Password',
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat new password'}),
        label='Confirm Password',
    )

    class Meta:
        model = User  # replace with your actual User model
        fields = ['barangay', 'username']  # add any other editable fields here

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password or confirm_password:
            if password != confirm_password:
                raise forms.ValidationError("Passwords do not match.")
            if len(password) < 8:
                raise forms.ValidationError("Password must be at least 8 characters.")

        return cleaned_data
    
# ----------------- Program Form -----------------
class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. AICS, AKAP, Disaster Relief'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Brief description of this program'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# ----------------- AidCategory Form -----------------
class AidCategoryForm(forms.ModelForm):
    class Meta:
        model = AidCategory
        fields = ['program', 'name', 'description', 'is_active']
        widgets = {
            'program': forms.Select(attrs={
                'class': 'form-select'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Medical, Burial, Food Packs'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# ----------------- Assistance Form -----------------
class AssistanceForm(forms.ModelForm):
    class Meta:
        model = Assistance
        fields = ['program', 'aid_category', 'beneficiary_type', 'minimum_age', 'is_active']
        widgets = {
            'program': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_program'
            }),
            'aid_category': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_aid_category'
            }),
            'beneficiary_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'minimum_age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Leave blank if no age requirement'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On load, only show categories for the selected program
        # JavaScript handles dynamic filtering on the frontend
        self.fields['aid_category'].queryset = AidCategory.objects.select_related('program').all()
        self.fields['minimum_age'].required = False

    def clean(self):
        cleaned_data = super().clean()
        beneficiary_type = cleaned_data.get('beneficiary_type')
        minimum_age = cleaned_data.get('minimum_age')

        # minimum_age only makes sense for individual-based assistance
        if beneficiary_type == 'family' and minimum_age:
            raise forms.ValidationError(
                "Minimum age is only applicable for individual-based assistance."
            )
        return cleaned_data
