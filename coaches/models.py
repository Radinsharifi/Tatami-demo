from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
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
