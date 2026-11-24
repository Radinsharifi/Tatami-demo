from django import forms
from django.forms import BaseInlineFormSet

from accounts.phone import normalize_gym_phone

from .models import Gym, GymCoachPlaceholder


class GymForm(forms.ModelForm):
	"""The shared club-creation form: used by the owner flow and the admin.

	Subordinates (coaches/students) are deliberately absent: empty lists
	must never block creation.
	"""

	class Meta:
		model = Gym
		fields = ('name', 'phone', 'address', 'latitude', 'longitude')
		widgets = {
			'name': forms.TextInput(attrs={'placeholder': 'مثلاً باشگاه آزادی'}),
			'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'نشانی کامل باشگاه'}),
			'latitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'مثلاً 35.721900'}),
			'longitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'مثلاً 51.389000'}),
		}

	# Phone normalization/validation is `Gym.clean()`'s job so the admin's
	# generated form behaves identically; a field-level `clean_phone` here
	# would only duplicate the error message.


class GymCoachPlaceholderForm(forms.ModelForm):
	"""Add a coach who has no Tatami Plus account yet (text roster entry)."""

	class Meta:
		model = GymCoachPlaceholder
		fields = ('name', 'phone')
		widgets = {
			'name': forms.TextInput(attrs={'placeholder': 'نام مربی'}),
			'phone': forms.TextInput(attrs={'placeholder': '۰۹۱۲… (اختیاری)'}),
		}

	def clean_phone(self):
		phone = (self.cleaned_data.get('phone') or '').strip()
		if not phone:
			return ''
		try:
			return normalize_gym_phone(phone)
		except ValueError as exc:
			raise forms.ValidationError(str(exc)) from exc


class LinkCoachForm(forms.Form):
	"""Link an existing coach account by phone number.

	The phone lookup keeps `gyms` free of any `coaches` import (the reverse
	`portfolio` relation is read at runtime, exactly like `accounts` does),
	so the dependency stays one-way: coaches → gyms.
	"""

	phone = forms.CharField(
		label='شمارهٔ همراه مربی',
		max_length=20,
		widget=forms.TextInput(attrs={'placeholder': '۰۹۱۲۳۴۵۶۷۸۹'}),
		help_text='مربی باید قبلاً در تاتامی پلاس ثبت‌نام کرده باشد؛ در غیر این صورت او را به‌صورت متنی اضافه کنید.',
	)

	def clean_phone(self):
		try:
			return normalize_gym_phone(self.cleaned_data['phone'])
		except ValueError as exc:
			raise forms.ValidationError(str(exc)) from exc


class GymWorkingHourFormSet(BaseInlineFormSet):
	"""Reject duplicate days: on add, rows are saved before the unique
	constraint can be checked against the not-yet-saved club.

	The admin inline wires this class through `inlineformset_factory`
	internally (`GymWorkingHourInline.formset`), so no factory lives here.
	"""

	def clean(self):
		super().clean()
		if any(self.errors):
			return
		seen = set()
		for form in self.forms:
			if not form.cleaned_data or form.cleaned_data.get('DELETE'):
				continue
			day = form.cleaned_data.get('day')
			if day is None:
				continue
			if day in seen:
				raise forms.ValidationError('هر روز هفته فقط یک بار می‌تواند ثبت شود.')
			seen.add(day)
