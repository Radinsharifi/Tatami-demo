from django.test import TestCase

# Create your tests here.
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
import jdatetime

from .models import CoachApplication, CoachProfile


class CoachWorkflowTests(TestCase):
	def create_application(self, username='coach-user'):
		user = get_user_model().objects.create_user(
			username=username,
			password='Safe-Training-Password-914!',
			role=get_user_model().Role.COACH,
		)
		application = CoachApplication(
			user=user,
			coaching_level='Advanced',
			specializations='Taekwondo',
			years_experience=8,
			club_name='Local club',
			certificate_details='National coaching certificate',
			certificate_document=SimpleUploadedFile('certificate.pdf', b'%PDF-1.4 test document'),
		)
		application.full_clean()
		application.save()
		self.addCleanup(application.certificate_document.delete, save=False)
		return application

	def test_coach_can_submit_one_pending_application(self):
		user = get_user_model().objects.create_user(
			username='applicant',
			password='Safe-Training-Password-914!',
			role=get_user_model().Role.COACH,
		)
		self.client.force_login(user)
		response = self.client.post(
			reverse('coaches:apply'),
			{
				'coaching_level': 'Advanced',
				'specializations': 'Taekwondo',
				'years_experience': 8,
				'club_name': 'Local club',
				'certificate_details': 'National coaching certificate',
				'certificate_document': SimpleUploadedFile('certificate.pdf', b'%PDF-1.4 test document'),
			},
		)

		self.assertRedirects(response, reverse('coaches:application_status'))
		application = CoachApplication.objects.get(user=user)
		self.assertEqual(application.status, CoachApplication.Status.PENDING_REVIEW)
		with self.assertRaises(ValueError):
			application.certificate_document.url
		self.addCleanup(application.certificate_document.delete, save=False)

		response = self.client.get(reverse('coaches:apply'))
		self.assertRedirects(response, reverse('coaches:application_status'))

	def test_student_cannot_submit_coach_application(self):
		student = get_user_model().objects.create_user(
			username='student-user',
			password='Safe-Training-Password-914!',
		)
		self.client.force_login(student)

		response = self.client.get(reverse('coaches:apply'))

		self.assertEqual(response.status_code, 403)

	def test_rejection_requires_a_reason(self):
		application = self.create_application()
		application.status = CoachApplication.Status.REJECTED

		with self.assertRaises(ValidationError):
			application.full_clean()

	def test_only_approved_published_profiles_are_public(self):
		application = self.create_application()
		profile = CoachProfile.objects.create(
			application=application,
			display_name='Coach Example',
			biography='A team-managed profile.',
		)
		self.assertEqual(self.client.get(reverse('coaches:directory')).status_code, 200)
		self.assertEqual(
			self.client.get(reverse('coaches:profile_detail', args=[profile.pk])).status_code,
			404,
		)

		application.status = CoachApplication.Status.APPROVED
		application.save()
		profile.is_published = True
		profile.full_clean()
		profile.save()

		response = self.client.get(reverse('coaches:directory'))
		self.assertContains(response, 'Coach Example')
		self.assertEqual(
			self.client.get(reverse('coaches:profile_detail', args=[profile.pk])).status_code,
			200,
		)

		application.status = CoachApplication.Status.REJECTED
		application.rejection_reason = 'Review did not pass.'
		application.save()
		self.assertNotContains(self.client.get(reverse('coaches:directory')), 'Coach Example')

	def test_certificate_download_is_staff_only(self):
		application = self.create_application()
		url = reverse('coaches:certificate_download', args=[application.pk])

		self.assertEqual(self.client.get(url).status_code, 302)

		staff = get_user_model().objects.create_superuser(
			phone='09120000120',
			password='Safe-Training-Password-914!',
		)
		self.client.force_login(staff)
		response = self.client.get(url)

		self.assertEqual(response.status_code, 200)
		self.assertIn('attachment', response.headers['Content-Disposition'])
		self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4 test document')

	def test_application_status_uses_persian_jalali_date(self):
		application = self.create_application()
		application.submitted_at = jdatetime.datetime(
			1405,
			8,
			11,
			8,
			tzinfo=timezone.get_current_timezone(),
		)
		application.save(update_fields=['submitted_at'])
		self.client.force_login(application.user)

		response = self.client.get(reverse('coaches:application_status'))

		self.assertContains(response, 'تاریخ ثبت: ۱۴۰۵/۰۸/۱۱')


class CoachAdminLocalizationTests(TestCase):
	def test_coach_admin_changelist_renders_jalali_date_filters(self):
		staff = get_user_model().objects.create_superuser(
			phone='09120000150',
			password='Safe-Training-Password-914!',
		)
		self.client.force_login(staff)

		response = self.client.get(reverse('admin:coaches_coachapplication_changelist'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'زمان ثبت')
