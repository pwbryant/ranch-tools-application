from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

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
    search_rfid = forms.CharField(
        label='EID',
        required=False,
        widget=forms.TextInput(attrs={'autofocus': 'autofocus'})
    )


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
    should_sell = forms.BooleanField(label='Should Sell', required=False, widget=forms.CheckboxInput())

    class Meta:
        model = PregCheck
        fields = ['is_pregnant', 'breeding_season', 'comments', 'recheck', 'check_date', 'should_sell']
        widgets = {
            'is_pregnant': forms.RadioSelect(choices=((True, 'Pregnant'), (False, 'Open'))),
            'breeding_season': forms.TextInput(attrs={'pattern': r'\d{4}', 'title': 'Please enter a four-digit year'}),
            'comments': forms.Textarea(attrs={'rows': 2}),
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
        label='EID (optional)',
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'placeholer': 'RFID'})
    )
    birth_year = forms.CharField(
        label='Birth Year (optional)',
        max_length=4,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'YYYY'})
    )

    def clean_eid(self):
        eid = self.cleaned_data.get('eid')
        if eid == '':
            return None
        return eid


class EditPregCheckForm(forms.ModelForm):
    ear_tag_id = forms.CharField(max_length=10, required=False)
    birth_year = forms.IntegerField(validators=[
        MinValueValidator(1000),
        MaxValueValidator(9999)
    ], required=False)
    breeding_season = forms.IntegerField(validators=[
        MinValueValidator(1000),
        MaxValueValidator(9999)
    ])
    new_cow = forms.BooleanField(label='Create new cow if not found', required=False)

    class Meta:
        model = PregCheck
        fields = ['ear_tag_id', 'birth_year', 'check_date', 'breeding_season', 'is_pregnant', 'comments', 'recheck', 'should_sell']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.cow:
            self.fields['ear_tag_id'].initial = self.instance.cow.ear_tag_id
            self.fields['birth_year'].initial = self.instance.cow.birth_year

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        recheck = cleaned_data.get('recheck')
        ear_tag_id = cleaned_data.get('ear_tag_id')
        birth_year = cleaned_data.get('birth_year')
        new_cow = cleaned_data.get('new_cow', False)

        if new_cow and recheck:
            raise ValidationError("Cannot mark as recheck: no previous non-recheck PregCheck")

        # Skip existence check if user intends to create a new cow
        if new_cow:
            return cleaned_data

        cow = None
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

        if recheck and cow is not None:
            breeding_season = cleaned_data['breeding_season']
            previous_pregchecks = PregCheck.objects.filter(
                cow=cow,
                breeding_season=breeding_season,
            ).order_by('check_date')
            if str(previous_pregchecks[0].id) == self.data['pregcheck_id']:
                raise ValidationError(
                    "Cannot mark as recheck: no previous non-recheck PregCheck "
                    f"found for {cow} in breeding season {breeding_season}"
                )

        return cleaned_data

    def save(self, commit=True):
        preg_check = super().save(commit=False)
        ear_tag_id = self.cleaned_data.get('ear_tag_id')
        birth_year = self.cleaned_data.get('birth_year')
        new_cow = self.cleaned_data.get('new_cow', False)
        
        if ear_tag_id and birth_year:
            try:
                cow = Cow.objects.get(ear_tag_id=ear_tag_id, birth_year=birth_year)
                preg_check.cow = cow
            except Cow.DoesNotExist:
                if new_cow:
                    # Create a new cow record
                    cow = Cow.objects.create(
                        ear_tag_id=ear_tag_id,
                        birth_year=birth_year if birth_year else None
                    )
                    preg_check.cow = cow
                else:
                    raise ValidationError(f"No cow found with ear_tag_id {ear_tag_id}")
        
        if commit:
            preg_check.save()
        return preg_check
