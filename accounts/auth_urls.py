from django.urls import path

from . import views

app_name = 'phone_auth'

urlpatterns = [
	path('login/', views.phone_login, name='login'),
	path('otp/send/', views.send_otp_view, name='send_otp'),
	path('otp/verify/', views.verify_otp_view, name='verify_otp'),
	path('complete-profile/', views.complete_profile, name='complete_profile'),
]