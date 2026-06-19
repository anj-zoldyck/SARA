from django import forms
from .models import User, Barangay

class UserInvitationForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('MSWDO_STAFF', 'MSWDO Staff'),
        ('BARANGAY', 'Barangay Admin'),
    )
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.all(),
        empty_label="Select Barangay",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'role', 'barangay']

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        barangay = cleaned_data.get('barangay')
        email = cleaned_data.get('email')

        if role == 'BARANGAY':
            if not barangay:
                self.add_error('barangay', "Barangay is required for Barangay Admin role.")
            else:
                # Check if barangay is already assigned to an active/pending Barangay Admin
                if User.objects.filter(role='BARANGAY', barangay=barangay).exclude(pk=self.instance.pk).exists():
                    self.add_error('barangay', f"{barangay.name} already has an assigned Barangay Admin account.")
        
        elif role == 'MSWDO_STAFF':
            # Remove barangay if provided for MSWDO_STAFF
            cleaned_data['barangay'] = None
            if email:
                if User.objects.filter(role='MSWDO_STAFF', email=email).exclude(pk=self.instance.pk).exists():
                    self.add_error('email', "An MSWDO Staff account with this email already exists.")
                    
        return cleaned_data

class UserEditForm(forms.ModelForm):
    """
    Edit form for an existing user account from the admin side.
    Password is optional — leave blank to keep the current password.
    """
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    role = forms.CharField(disabled=True, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.all(),
        empty_label="Unassigned",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Leave blank to keep current password', 'class': 'form-control'}),
        label='New Password',
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat new password', 'class': 'form-control'}),
        label='Confirm Password',
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'role', 'barangay']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        barangay = cleaned_data.get('barangay')
        
        # Enforce barangay unicity on edit for BARANGAY
        if self.instance.role == 'BARANGAY' and barangay:
             if User.objects.filter(role='BARANGAY', barangay=barangay).exclude(pk=self.instance.pk).exists():
                 self.add_error('barangay', f"{barangay.name} already has an assigned Barangay Admin account.")

        if password or confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            if password and len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters.")

        return cleaned_data

# ============================================================
# Profile self-service forms (for logged-in users to edit their own profile)

from django.contrib.auth import password_validation


class ProfileSettingsForm(forms.ModelForm):
    """
    Self-service profile edit form, shared by all 3 roles
    (MSWDO Admin, MSWDO Staff, Barangay Admin).

    Role-based field locking is handled in __init__:
    - username: editable ONLY for MSWDO Admin. Read-only for
      MSWDO_STAFF and BARANGAY (displayed via template, not
      via a disabled form field, to avoid posting back a
      disabled field's value as empty).
    - barangay: never editable here (admin-assigned only).
      Shown as read-only context in the template, not a form field.
    - position: editable for ALL roles.
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
    profile_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'})
    )
    username = forms.CharField(
        required=False,
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
            'profile_image',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Username is editable ONLY by MSWDO Admin.
        # For other roles, remove it from the form entirely so a
        # crafted/duplicated POST can't sneak through a username change.
        if self.instance.role != 'MSWDO':
            del self.fields['username']

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email

    def clean_username(self):
        # Only present for MSWDO Admin (see __init__); still guard uniqueness.
        username = self.cleaned_data.get('username')
        if username:
            qs = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This username is already taken.")
        return username


class ProfilePasswordChangeForm(forms.Form):
    """
    Self-service password change. Requires the user's CURRENT password
    (unlike the admin-side UserEditForm reset, which doesn't need it,
    since an admin resetting someone else's password doesn't need to
    know their old one). This prevents an unattended logged-in session
    from being used to silently take over the account.
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
