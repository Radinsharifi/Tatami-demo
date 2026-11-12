from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django_jalali.db import models as jmodels
from .storage import PrivateUploadStorage

private_storage = PrivateUploadStorage()


class CoachApplication(models.Model):
	objects = jmodels.jManager()

	class Status(models.TextChoices):
		PENDING_REVIEW = 'pending_review', 'در انتظار بررسی'
		APPROVED = 'approved', 'تأییدشده'
		REJECTED = 'rejected', 'ردشده'

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='coach_application',
		verbose_name='کاربر مربی',
	)
	coaching_level = models.CharField('سطح مربیگری', max_length=100)
	specializations = models.TextField('تخصص‌ها')
	years_experience = models.PositiveSmallIntegerField('سابقهٔ مربیگری، به سال')
	club_name = models.CharField('نام باشگاه', max_length=150, blank=True)
	certificate_details = models.TextField('توضیحات مدارک')
	certificate_document = models.FileField(
		'فایل مدرک',
		storage=private_storage,
		upload_to='coach-certificates/%Y/%m/',
		validators=[FileExtensionValidator(
			['pdf', 'jpg', 'jpeg', 'png'],
			message='فقط فایل PDF یا تصویر JPG و PNG مجاز است.',
		)],
	)
	status = models.CharField(
		'وضعیت درخواست',
		max_length=20,
		choices=Status.choices,
		default=Status.PENDING_REVIEW,
	)
	rejection_reason = models.TextField('دلیل رد درخواست', blank=True)
	submitted_at = jmodels.jDateTimeField('زمان ثبت', auto_now_add=True)
	reviewed_at = jmodels.jDateTimeField('زمان بررسی', null=True, blank=True)

	class Meta:
		verbose_name = 'درخواست مربیگری'
		verbose_name_plural = 'درخواست‌های مربیگری'
		ordering = ['-submitted_at']

	def clean(self):
		super().clean()
		if self.user_id and self.user.role != self.user.Role.COACH:
			raise ValidationError({'user': 'فقط حساب مربی می‌تواند درخواست مربیگری ثبت کند.'})
		if self.status == self.Status.REJECTED and not self.rejection_reason.strip():
			raise ValidationError({'rejection_reason': 'برای رد درخواست، دلیل را وارد کنید.'})

	def __str__(self):
		return f'{self.user.username} ({self.get_status_display()})'


class CoachProfile(models.Model):
	objects = jmodels.jManager()

	application = models.OneToOneField(
		CoachApplication,
		on_delete=models.CASCADE,
		related_name='profile',
		verbose_name='درخواست مربیگری',
	)
	display_name = models.CharField('نام نمایشی', max_length=100)
	headline = models.CharField('عنوان کوتاه', max_length=180, blank=True)
	biography = models.TextField('معرفی مربی')
	belt = models.CharField('درجه', max_length=40, blank=True)
	club = models.CharField('باشگاه', max_length=150, blank=True)
	avatar = models.ImageField('تصویر', upload_to='coaches/avatars/%Y/%m/', blank=True)
	is_published = models.BooleanField('انتشار پروفایل', default=False)
	created_at = jmodels.jDateTimeField('زمان ایجاد', auto_now_add=True)
	updated_at = jmodels.jDateTimeField('آخرین ویرایش', auto_now=True)

	class Meta:
		verbose_name = 'پروفایل مربی'
		verbose_name_plural = 'پروفایل‌های مربیان'
		ordering = ['display_name']

	def clean(self):
		super().clean()
		if self.is_published and self.application.status != CoachApplication.Status.APPROVED:
			raise ValidationError({'is_published': 'پیش از انتشار پروفایل، درخواست مربی باید تأیید شود.'})

	def __str__(self):
		return self.display_name


class CoachInvite(models.Model):
	"""A shareable code a coach hands out so students can attach themselves.

	One coach can hold several codes: a permanent one with no use limit, a
	classroom code capped at 15 uses, or a time-limited campaign code. Codes
	are stored uppercase and looked up case-insensitively, because people read
	them off a screen and type them by hand.
	"""

	objects = jmodels.jManager()

	coach = models.ForeignKey(
		CoachProfile,
		verbose_name='مربی',
		on_delete=models.CASCADE,
		related_name='invites',
	)
	code = models.CharField('کد دعوت', max_length=12, unique=True)
	label = models.CharField('برچسب', max_length=80, blank=True, help_text='مثلاً «کلاس شنبه‌ها».')
	max_uses = models.PositiveSmallIntegerField('سقف استفاده', default=0, help_text='۰ یعنی بی‌نهایت.')
	uses = models.PositiveSmallIntegerField('تعداد استفاده', default=0, editable=False)
	is_active = models.BooleanField('فعال', default=True)
	expires_at = jmodels.jDateTimeField('انقضا', null=True, blank=True)
	created_at = jmodels.jDateTimeField('زمان ساخت', auto_now_add=True)

	class Meta:
		verbose_name = 'کد دعوت مربی'
		verbose_name_plural = 'کدهای دعوت مربیان'
		ordering = ['-created_at']

	@property
	def is_expired(self):
		return self.expires_at is not None and self.expires_at < timezone.now()

	@property
	def is_exhausted(self):
		return bool(self.max_uses) and self.uses >= self.max_uses

	@property
	def is_usable(self):
		return self.is_active and not self.is_expired and not self.is_exhausted

	def __str__(self):
		return f'{self.coach.display_name} — {self.code}'


class CoachStudent(models.Model):
	"""A student attached to a coach, created by redeeming an invite code.

	This is the first real student-coach relationship in the product, so the
	unique constraint is deliberate: one row per pair, no duplicates from a
	re-used code.
	"""

	objects = jmodels.jManager()

	coach = models.ForeignKey(
		CoachProfile,
		verbose_name='مربی',
		on_delete=models.CASCADE,
		related_name='students',
	)
	student = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		verbose_name='هنرجو',
		on_delete=models.CASCADE,
		related_name='coach_links',
	)
	invite = models.ForeignKey(
		CoachInvite,
		verbose_name='کد دعوت',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='students',
	)
	created_at = jmodels.jDateTimeField('زمان عضویت', auto_now_add=True)

	class Meta:
		verbose_name = 'هنرجوی مربی'
		verbose_name_plural = 'هنرجوهای مربی'
		ordering = ['-created_at']
		constraints = [
			models.UniqueConstraint(fields=['coach', 'student'], name='unique_student_per_coach'),
		]

	def __str__(self):
		return f'{self.student} → {self.coach.display_name}'
