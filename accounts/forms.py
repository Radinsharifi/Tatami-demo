import re

from django import forms

from .models import User
from .phone import normalize_iranian_phone


class PhoneLoginForm(forms.Form):
    phone = forms.CharField(label='شمارهٔ همراه', max_length=20)
    role = forms.ChoiceField(
        label='نقش کاربری',
        choices=User.Role.choices,
        initial=User.Role.STUDENT,
    )
    next_url = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_phone(self):
        try:
            return normalize_iranian_phone(self.cleaned_data['phone'])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_role(self):
        role = self.cleaned_data['role']
        if role not in User.Role.values:
            raise forms.ValidationError('نقش انتخاب‌شده معتبر نیست.')
        return role


class OTPVerifyForm(forms.Form):
    code = forms.CharField(label='کد یک‌بارمصرف', max_length=8)

    def clean_code(self):
        code = self.cleaned_data['code'].translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
        if not re.fullmatch(r'\d{5}', code):
            raise forms.ValidationError('کد باید پنج رقم باشد.')
        return code


class ProfileCompletionForm(forms.Form):
    name = forms.CharField(label='نام', max_length=150)
    city = forms.CharField(label='شهر', max_length=100)
    role = forms.ChoiceField(label='نقش کاربری', choices=User.Role.choices)

    def save(self, user):
        user.first_name = self.cleaned_data['name'].strip()
        user.city = self.cleaned_data['city'].strip()
        user.role = self.cleaned_data['role']
        user.is_profile_complete = True
        user.save(update_fields=['first_name', 'city', 'role', 'is_profile_complete'])
        return user