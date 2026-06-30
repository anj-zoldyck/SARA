from django import forms
from .models import User, Barangay
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.shortcuts import render, redirect
from django.contrib import messages


class UserInvitationForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('MSWDO_STAFF', 'MSWDO Staff'),
        ('BARANGAY', 'Barangay Admin'),
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.none(),  # set properly in __init__
        empty_label="Select Barangay",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
 
    class Meta:
        model = User
        fields = ['email', 'role', 'barangay']
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['barangay'].queryset = Barangay.objects.all()
 
    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        barangay = cleaned_data.get('barangay')
        email = cleaned_data.get('email')
 
        if role == 'BARANGAY':
            if not barangay:
                self.add_error('barangay', "Barangay is required for Barangay Admin role.")
 
        elif role == 'MSWDO_STAFF':
            cleaned_data['barangay'] = None
            if email:
                if User.objects.filter(role='MSWDO_STAFF', email__iexact=email).exclude(pk=self.instance.pk).exists():
                    self.add_error('email', "An MSWDO Staff account with this email already exists.")
 
        return cleaned_data

class UserEditForm(forms.ModelForm):
    """
    Edit form for correcting an existing user's email from the admin side.
    """
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email

# ============================================================
# Profile self-service forms (for logged-in users to edit their own profile)

from django.contrib.auth import password_validation


class UserInvitationForm(forms.ModelForm):
    ROLE_CHOICES = (
        ('MSWDO_STAFF', 'MSWDO Staff'),
        ('BARANGAY', 'Barangay Admin'),
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.none(),  # set properly in __init__
        empty_label="Select Barangay",
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
 
    class Meta:
        model = User
        fields = ['email', 'role', 'barangay']
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
 
        # Only offer barangays that do NOT already have an assigned
        # admin (active OR still-pending-activation). This makes it
        # impossible to even select a taken barangay from the dropdown,
        # rather than relying solely on the clean() error message below.
        taken_barangay_ids = User.objects.filter(
            role='BARANGAY',
            barangay__isnull=False
        ).values_list('barangay_id', flat=True)
 
        self.fields['barangay'].queryset = Barangay.objects.exclude(
            id__in=taken_barangay_ids
        )
 
    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        barangay = cleaned_data.get('barangay')
        email = cleaned_data.get('email')
 
        if role == 'BARANGAY':
            if not barangay:
                self.add_error('barangay', "Barangay is required for Barangay Admin role.")
            else:
                # Re-check here too (not just the filtered queryset above) —
                # protects against a race condition where two invitations
                # are submitted for the same barangay at nearly the same time.
                if User.objects.filter(role='BARANGAY', barangay=barangay).exclude(pk=self.instance.pk).exists():
                    self.add_error('barangay', f"{barangay.name} already has an assigned Barangay Admin account.")
 
        elif role == 'MSWDO_STAFF':
            cleaned_data['barangay'] = None
            if email:
                if User.objects.filter(role='MSWDO_STAFF', email__iexact=email).exclude(pk=self.instance.pk).exists():
                    self.add_error('email', "An MSWDO Staff account with this email already exists.")
 
        return cleaned_data

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

class SetPasswordForm(forms.Form):
    """
    Used on the activation page. Since UserInvitationForm no longer
    collects a username (the admin only provides email + role +
    barangay), the invited user now chooses their own username here,
    at the same time they set their password.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="New Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="Confirm Password")
 
    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
 
    def clean_username(self):
        username = self.cleaned_data.get('username')
        qs = User.objects.filter(username__iexact=username)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username
 
    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('confirm_password'):
            raise forms.ValidationError("Passwords do not match.")
        if cleaned.get('password') and len(cleaned.get('password')) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        return cleaned
 
 
# View for handling the activation link with token verification and password setup

 
def activate_account(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
 
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user=user, data=request.POST)
            if form.is_valid():
                user.username = form.cleaned_data['username']
                user.set_password(form.cleaned_data['password'])
                user.is_active = True
                user.save()
                messages.success(request, "Account activated! You can now log in.")
                return redirect('login')
        else:
            form = SetPasswordForm(user=user)
        return render(request, 'accounts/activate_account.html', {'form': form})
    else:
        return render(request, 'accounts/activation_invalid.html')