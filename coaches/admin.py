from django.contrib import admin
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django_jalali.admin.filters import JDateFieldListFilter

# Register your models here.
from .models import CoachApplication, CoachProfile


@admin.register(CoachApplication)
class CoachApplicationAdmin(admin.ModelAdmin):
	list_display = ('user', 'coaching_level', 'status', 'submitted_at', 'reviewed_at')
	list_filter = (
		'status',
		'coaching_level',
		('submitted_at', JDateFieldListFilter),
		('reviewed_at', JDateFieldListFilter),
	)
	search_fields = ('user__username', 'user__email', 'club_name')
	readonly_fields = ('user', 'certificate_download', 'submitted_at', 'reviewed_at')
	fields = (
		'user',
		'coaching_level',
		'specializations',
		'years_experience',
		'club_name',
		'certificate_details',
		'certificate_download',
		'status',
		'rejection_reason',
		'submitted_at',
		'reviewed_at',
	)

	@admin.display(description='فایل مدرک')
	def certificate_download(self, application):
		if not application.certificate_document:
			return 'فایلی بارگذاری نشده است'
		url = reverse('coaches:certificate_download', args=[application.pk])
		return format_html('<a href="{}">دریافت فایل مدرک</a>', url)

	def save_model(self, request, obj, form, change):
		if obj.status in (CoachApplication.Status.APPROVED, CoachApplication.Status.REJECTED):
			obj.reviewed_at = obj.reviewed_at or timezone.now()
		else:
			obj.reviewed_at = None
		super().save_model(request, obj, form, change)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
	list_display = ('display_name', 'application', 'is_published', 'updated_at')
	list_filter = ('is_published',)
	search_fields = ('display_name', 'application__user__username')
	readonly_fields = ('created_at', 'updated_at')
