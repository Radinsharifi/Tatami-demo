from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django_jalali.db import models as jmodels


class User(AbstractUser):
	last_login = jmodels.jDateTimeField('آخرین ورود', blank=True, null=True)
	date_joined = jmodels.jDateTimeField('تاریخ عضویت', default=timezone.now)

	class Role(models.TextChoices):
		STUDENT = 'student', 'هنرجو'
		COACH = 'coach', 'مربی'

	role = models.CharField('نقش', max_length=10, choices=Role.choices, default=Role.STUDENT)

	class Meta:
		verbose_name = 'کاربر'
		verbose_name_plural = 'کاربران'

	def __str__(self):
		return self.username
