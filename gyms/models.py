from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django_jalali.db import models as jmodels

from accounts.phone import normalize_gym_phone


class Gym(models.Model):
	"""A physical sports club: one shared profile for both creation paths.

	The owner creates it from the site (`/gyms/new/`, role `gym`) or an admin
	creates it from «مدیریت باشگاه‌ها»; both produce the same row. `owner` is
	nullable because an admin-created club may not have an owner yet.
	"""

	objects = jmodels.jManager()

	class Status(models.TextChoices):
		ACTIVE = 'active', 'فعال'
		PENDING = 'pending', 'در انتظار تأیید'
		INACTIVE = 'inactive', 'غیرفعال'
		SUSPENDED = 'suspended', 'معلق'

	name = models.CharField('نام باشگاه', max_length=150)
	phone = models.CharField('تلفن باشگاه', max_length=11)
	address = models.TextField('نشانی')
	latitude = models.DecimalField(
		'عرض جغرافیایی',
		max_digits=9,
		decimal_places=6,
		validators=[MinValueValidator(-90), MaxValueValidator(90)],
	)
	longitude = models.DecimalField(
		'طول جغرافیایی',
		max_digits=9,
		decimal_places=6,
		validators=[MinValueValidator(-180), MaxValueValidator(180)],
	)
	owner = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		verbose_name='مالک باشگاه',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='owned_gyms',
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		verbose_name='سازندهٔ رکورد',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='gyms_created',
	)
	# Admin-created clubs start active; the owner flow passes pending
	# explicitly, so the initial status is decided by the creation method.
	status = models.CharField('وضعیت', max_length=20, choices=Status.choices, default=Status.ACTIVE)
	created_at = jmodels.jDateTimeField('زمان ایجاد', auto_now_add=True)
	updated_at = jmodels.jDateTimeField('آخرین ویرایش', auto_now=True)

	class Meta:
		verbose_name = 'باشگاه'
		verbose_name_plural = 'باشگاه‌ها'
		ordering = ['-created_at']

	def clean(self):
		"""Normalize and validate the contact number for both creation paths.

		Lives on the model (not the form) so the admin's generated form gets
		the same validation as the owner's `GymForm` (PRD rule 7).
		"""
		super().clean()
		if not self.phone:
			# The forms already report the required-field error; normalizing
			# an empty value here would only duplicate the message.
			return
		try:
			self.phone = normalize_gym_phone(self.phone)
		except ValueError as exc:
			raise ValidationError({'phone': str(exc)}) from exc

	def __str__(self):
		return self.name


class GymWorkingHour(models.Model):
	"""Seven weekly rows per club, created for every club on creation.

	Empty hours must never block a club, so `services.ensure_working_hours`
	fills any missing day with an editable default right after creation.
	"""

	objects = jmodels.jManager()

	class Day(models.IntegerChoices):
		SATURDAY = 0, 'شنبه'
		SUNDAY = 1, 'یکشنبه'
		MONDAY = 2, 'دوشنبه'
		TUESDAY = 3, 'سه‌شنبه'
		WEDNESDAY = 4, 'چهارشنبه'
		THURSDAY = 5, 'پنجشنبه'
		FRIDAY = 6, 'جمعه'

	gym = models.ForeignKey(
		Gym,
		verbose_name='باشگاه',
		on_delete=models.CASCADE,
		related_name='working_hours',
	)
	day = models.PositiveSmallIntegerField('روز هفته', choices=Day.choices)
	opens = models.TimeField('ساعت باز شدن', null=True, blank=True)
	closes = models.TimeField('ساعت بسته شدن', null=True, blank=True)
	is_closed = models.BooleanField('تعطیل', default=False)

	class Meta:
		verbose_name = 'ساعت کاری'
		verbose_name_plural = 'ساعات کاری'
		ordering = ['day']
		constraints = [
			models.UniqueConstraint(fields=['gym', 'day'], name='unique_day_per_gym'),
		]

	def clean(self):
		super().clean()
		if self.is_closed:
			return
		if self.opens is None or self.closes is None:
			raise ValidationError('برای روزهای باز، ساعت شروع و پایان را وارد کنید.')
		if self.closes <= self.opens:
			raise ValidationError('ساعت پایان باید بعد از ساعت شروع باشد.')

	def __str__(self):
		return f'{self.gym} — {self.get_day_display()}'


class GymStudent(models.Model):
	"""Schema-only link between a club and its students (UI comes later).

	Anticipated from day one per the PRD: empty lists never block creation,
	_but_ the relationship must exist in the database from the start.
	"""

	objects = jmodels.jManager()

	gym = models.ForeignKey(
		Gym,
		verbose_name='باشگاه',
		on_delete=models.CASCADE,
		related_name='student_links',
	)
	student = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		verbose_name='هنرجو',
		on_delete=models.CASCADE,
		related_name='gym_memberships',
	)
	created_at = jmodels.jDateTimeField('زمان عضویت', auto_now_add=True)

	class Meta:
		verbose_name = 'دانش‌آموز باشگاه'
		verbose_name_plural = 'دانش‌آموزان باشگاه'
		ordering = ['-created_at']
		constraints = [
			models.UniqueConstraint(fields=['gym', 'student'], name='unique_student_per_gym'),
		]

	def __str__(self):
		return f'{self.student} → {self.gym}'


class GymCoachPlaceholder(models.Model):
	"""A text-only roster entry for a coach without a Tatami Plus account.

	Gym coaches do not all exist in the app yet, so the roster holds both
	linked `CoachPortfolio` accounts (reverse `gym.coaches`) and these
	placeholder rows. A placeholder is converted into a real link once the
	coach signs up.
	"""

	objects = jmodels.jManager()

	gym = models.ForeignKey(
		Gym,
		verbose_name='باشگاه',
		on_delete=models.CASCADE,
		related_name='coach_placeholders',
	)
	name = models.CharField('نام مربی', max_length=150)
	# Optional: used later to match the placeholder to an account that signs
	# up with the same number.
	phone = models.CharField('تلفن', max_length=11, blank=True)
	created_at = jmodels.jDateTimeField('زمان ایجاد', auto_now_add=True)

	class Meta:
		verbose_name = 'مربی بدون حساب'
		verbose_name_plural = 'مربیان بدون حساب'
		ordering = ['name']
		constraints = [
			models.UniqueConstraint(
				fields=['gym', 'phone'],
				condition=~models.Q(phone=''),
				name='unique_placeholder_phone_per_gym',
			),
		]

	def __str__(self):
		return self.name
