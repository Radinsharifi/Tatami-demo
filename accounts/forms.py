from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'role')
        labels = {
            'username': 'نام کاربری',
            'email': 'رایانامه',
            'role': 'نقش کاربری',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'گذرواژه'
        self.fields['password1'].help_text = (
            'گذرواژه باید دست‌کم ۸ نویسه داشته باشد و به اطلاعات شخصی شما شبیه نباشد.'
        )
        self.fields['password2'].label = 'تکرار گذرواژه'
        self.fields['password2'].help_text = 'برای تأیید، گذرواژه را دوباره وارد کنید.'
        self.fields['username'].help_text = 'این نام برای ورود به حساب کاربری استفاده می‌شود.'


class LoginForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields['username'].label = 'نام کاربری'
        self.fields['password'].label = 'گذرواژه'