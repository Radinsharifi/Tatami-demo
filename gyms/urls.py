from django.urls import path

from . import views

app_name = 'gyms'

urlpatterns = [
	path('new/', views.create, name='create'),
	path('panel/', views.panel, name='panel'),
	path('panel/coaches/add/', views.coach_placeholder_add, name='coach_placeholder_add'),
	path('panel/coaches/link/', views.coach_link, name='coach_link'),
	path('panel/coaches/<int:pk>/remove/', views.coach_placeholder_remove, name='coach_placeholder_remove'),
	path('panel/coaches/<int:pk>/unlink/', views.coach_unlink, name='coach_unlink'),
]
