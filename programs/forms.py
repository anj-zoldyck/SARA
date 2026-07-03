from django import forms
from .models import Program, AidCategory, Assistance

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
        fields = ['program', 'aid_category', 'beneficiary_type', 'minimum_age', 'requires_pwd', 'requires_solo_parent', 'requires_senior_citizen', 'is_active']
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
            'requires_pwd': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'requires_solo_parent': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'requires_senior_citizen': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
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
