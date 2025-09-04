from django import forms
from django.core.exceptions import ValidationError

from .models import Cow, PregCheck

from pdb import set_trace as bp


class AnimalSearchForm(forms.Form):

    def __init__(self, *args, **kwargs):
        birth_year_choices = kwargs.pop('birth_year_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['search_birth_year'] = forms.ChoiceField(
            choices=birth_year_choices,
            widget=forms.RadioSelect,
            required=False
        )
    search_ear_tag_id = forms.CharField(label='Ear Tag ID', required=False)
    search_rfid = forms.CharField(label='RFID', required=False)


class PregCheckForm(forms.ModelForm):
    pregcheck_ear_tag_id = forms.CharField(label='Ear Tag ID', required=False)
    pregcheck_rfid = forms.CharField(label='RFID', required=False)
    birth_year = forms.CharField(required=False, widget=forms.HiddenInput())
    check_date = forms.DateField(label='Check Date', required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    is_pregnant = forms.ChoiceField(
        label='Status',
        choices=((True, 'Pregnant'), (False, 'Open')),
        widget=forms.RadioSelect(),
        required=True,
    )
    recheck = forms.BooleanField(label='Recheck', required=False, widget=forms.CheckboxInput())

    class Meta:
        model = PregCheck
        fields = ['is_pregnant', 'breeding_season', 'comments', 'recheck', 'check_date']
        widgets = {
            'is_pregnant': forms.RadioSelect(choices=((True, 'Pregnant'), (False, 'Open'))),
            'breeding_season': forms.TextInput(attrs={'pattern': r'\d{4}', 'title': 'Please enter a four-digit year'}),
            'comments': forms.Textarea,
        }


class CowForm(forms.ModelForm):
    class Meta:
        model = Cow
        fields = ['ear_tag_id', 'birth_year', 'eid']

    ear_tag_id = forms.CharField(
        label='Ear Tag ID',
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    eid = forms.CharField(
        label='RFID (optional)',
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'placeholer': 'RFID'})
    )
    birth_year = forms.CharField(
        label='Birth Year (optional)',
        max_length=4,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'YYYY'})
    )


class EditPregCheckForm(forms.ModelForm):
    ear_tag_id = forms.CharField(max_length=10, required=False)
    birth_year = forms.CharField(max_length=4, required=False)

    class Meta:
        model = PregCheck
        fields = ['ear_tag_id', 'birth_year', 'check_date', 'breeding_season', 'is_pregnant', 'comments', 'recheck']

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance.cow:
                self.fields['ear_tag_id'].initial = self.instance.cow.ear_tag_id
                self.fields['birth_year'].initial = self.instance.cow.birth_year

    def clean(self):
        cleaned_data = super().clean()
        ear_tag_id = cleaned_data.get('ear_tag_id')
        birth_year = cleaned_data.get('birth_year')
        if ear_tag_id and birth_year:
            try:
                cow = Cow.objects.get(ear_tag_id=ear_tag_id, birth_year=birth_year)
            except Cow.DoesNotExist:
                raise ValidationError(f"No cow found with ear_tag_id {ear_tag_id} and birth_year {birth_year}")
        elif ear_tag_id:
            try:
                cow = Cow.objects.get(ear_tag_id=ear_tag_id)
            except Cow.DoesNotExist:
                raise ValidationError(f"No cow found with ear_tag_id {ear_tag_id}")

        return cleaned_data

    def save(self, commit=True):
        preg_check = super().save(commit=False)
        ear_tag_id = self.cleaned_data.get('ear_tag_id')
        birth_year = self.cleaned_data.get('birth_year')
        
        if ear_tag_id:
            try:
                cow = Cow.objects.get(ear_tag_id=ear_tag_id, birth_year=birth_year)
                preg_check.cow = cow
            except Cow.DoesNotExist:
                # This shouldn't happen due to clean_ear_tag_id, but just in case
                raise ValidationError(f"No cow found with ear_tag_id {ear_tag_id}")

        if commit:
            preg_check.save()
        return preg_check
