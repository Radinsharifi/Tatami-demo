from django import forms

from .models import CoachApplication


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
		}

	def clean_certificate_document(self):
		document = self.cleaned_data['certificate_document']
		if document.size > 10 * 1024 * 1024:
			raise forms.ValidationError('حجم فایل مدرک نباید بیشتر از ۱۰ مگابایت باشد.')
		return document