from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter

from .forms import GymWorkingHourFormSet
from .models import Gym, GymWorkingHour
from .services import ensure_working_hours


class GymWorkingHourInline(admin.TabularInline):
	model = GymWorkingHour
	formset = GymWorkingHourFormSet
	fields = ('day', 'opens', 'closes', 'is_closed')
	extra = 7

	def get_extra(self, request, obj=None, **kwargs):
		# On change the seven rows already exist; on add offer one row per day.
		return 0 if obj else 7


@admin.register(Gym)
class GymAdmin(admin.ModelAdmin):
	"""«مدیریت باشگاه‌ها»: the PRD's second creation path (admin adds a club)."""

	list_display = ('name', 'phone', 'status', 'owner', 'created_at')
	list_filter = ('status', ('created_at', JDateFieldListFilter))
	search_fields = ('name', 'phone', 'address')
	fields = (
		'name',
		'phone',
		'address',
		'latitude',
		'longitude',
		'status',
		'owner',
		'created_by',
		'created_at',
		'updated_at',
	)
	readonly_fields = ('created_by', 'created_at', 'updated_at')
	inlines = [GymWorkingHourInline]

	def save_model(self, request, obj, form, change):
		if not change:
			obj.created_by = request.user
		super().save_model(request, obj, form, change)

	def save_related(self, request, form, formsets, change):
		super().save_related(request, form, formsets, change)
		# Days the admin left blank get the defaults, so every club ends up
		# with its seven weekly rows no matter how the form was filled.
		ensure_working_hours(form.instance)
