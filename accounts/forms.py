from django import forms
from .models import User, Barangay
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.shortcuts import render, redirect
from django.contrib import messages


class CreateUserForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('MSWDO_STAFF', 'MSWDO Staff'),
        ('BARANGAY', 'Barangay Admin'),
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.none(),
        empty_label="Select Barangay",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'middle_name', 'suffix',
            'sex', 'birthdate', 'birth_place', 'civil_status', 'citizenship', 'contact_number',
            'role', 'barangay', 'position'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Middle Name (Optional)'}),
            'suffix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Jr, Sr (Optional)'}),
            'sex': forms.Select(attrs={'class': 'form-select'}),
            'birthdate': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'birth_place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Place of Birth'}),
            'civil_status': forms.Select(attrs={'class': 'form-select'}),
            'citizenship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Citizenship'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '09XXXXXXXXX'}),
            'position': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Job Position'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['barangay'].queryset = Barangay.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        barangay = cleaned_data.get('barangay')
        
        if role == 'BARANGAY':
            if not barangay:
                self.add_error('barangay', "Barangay is required for Barangay Admin role.")
        elif role == 'MSWDO_STAFF':
            cleaned_data['barangay'] = None
        
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

# ============================================================
# Profile self-service forms (for logged-in users to edit their own profile)

from django.contrib.auth import password_validation



#-------Profile Setting Form---------
class ProfileSettingsForm(forms.ModelForm):
    """
    Self-service profile edit form, shared by all 3 roles
    (MSWDO Admin, MSWDO Staff, Barangay Admin).
 
    Username is now editable by every role (per updated requirements).
    Barangay assignment is still never editable here — it remains
    admin-assigned only, shown as read-only context in the template.
    """
 
    middle_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Middle Name (optional)'})
    )
    suffix = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Jr., Sr., II'})
    )
    position = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Social Worker II'})
    )
    sex = forms.ChoiceField(
        choices=[('', '-- Select --')] + list(User.SEX_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    birthdate = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    contact_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '09XXXXXXXXX'})
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
 
    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'middle_name', 'suffix',
            'email', 'position', 'sex', 'birthdate', 'contact_number',
        ]
 
    # NOTE: __init__ override that deleted self.fields['username'] for
    # non-MSWDO roles has been removed. Username is now editable by
    # everyone; uniqueness is still enforced in clean_username() below.
 
    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email
 
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            qs = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This username is already taken.")
        return username

class ProfilePasswordChangeForm(forms.Form):
    """
    Self-service password change. Requires the user's CURRENT password.
    This prevents an unattended logged-in session from being used to
    silently take over the account.
    """
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Current Password'})
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'New Password'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm New Password'})
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise forms.ValidationError("Your current password is incorrect.")
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password:
            if new_password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                # Reuse Django's built-in password validators
                # (AUTH_PASSWORD_VALIDATORS in settings.py) for consistency
                # with the rest of the system instead of a hardcoded length check.
                try:
                    password_validation.validate_password(new_password, self.user)
                except forms.ValidationError as e:
                    self.add_error('new_password', e)

        return cleaned_data