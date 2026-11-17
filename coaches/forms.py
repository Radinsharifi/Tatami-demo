import re

from django import forms

from coaches.storage import PrivateFileInput

from .models import CoachApplication, CoachInvite, CoachProfile


class CoachApplicationForm(forms.ModelForm):
	class Meta:
		model = CoachApplication
		fields = (
			'coaching_level',
			'specializations',
			'years_experience',
			'club_name',
			'certificate_details',
			'certificate_document',
		)
		widgets = {
			'specializations': forms.Textarea(attrs={'rows': 3}),
			'certificate_details': forms.Textarea(attrs={'rows': 3}),
			# The certificate is private; the default widget would call `.url()`.
			'certificate_document': PrivateFileInput,
		}

	def clean_certificate_document(self):
		document = self.cleaned_data['certificate_document']
		if document.size > 10 * 1024 * 1024:
			raise forms.ValidationError('حجم فایل مدرک نباید بیشتر از ۱۰ مگابایت باشد.')
		return document


class CoachInviteForm(forms.ModelForm):
	"""Create a code. The code itself and the use counter are system-owned."""

	class Meta:
		model = CoachInvite
		fields = ('label', 'max_uses')
		widgets = {
			'label': forms.TextInput(attrs={'placeholder': 'مثلاً کلاس شنبه‌ها'}),
		}


class InviteCodeEntryForm(forms.Form):
	"""A student who was told a code by hand, rather than sent a link."""

	code = forms.CharField(
		label='کد دعوت',
		max_length=12,
		widget=forms.TextInput(attrs={
			'placeholder': 'مثلاً K7PM2XQ9',
			'autocomplete': 'off',
			'autocapitalize': 'characters',
		}),
	)

	def clean_code(self):
		# Codes are stored uppercase and looked up case-insensitively; accept
		# Persian/Arabic digits by folding them first.
		code = self.cleaned_data['code'].strip().upper()
		code = code.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
		if not re.fullmatch(r'[A-Z0-9]{4,12}', code):
			raise forms.ValidationError('کد دعوت باید ۸ نویسهٔ انگلیسی یا رقم باشد.')
		return code


class CoachProfileForm(forms.ModelForm):
	"""The coach's own public profile.

	`is_published` is deliberately absent: the team still decides when the
	profile goes live, so the coach can prepare it without publishing.
	"""

	class Meta:
		model = CoachProfile
		fields = ('display_name', 'headline', 'biography', 'belt', 'club', 'avatar')
		widgets = {
			'headline': forms.TextInput(attrs={'placeholder': 'مثلاً مربی کاتا و کیهوکوشین'}),
			'biography': forms.Textarea(attrs={'rows': 5}),
		}
