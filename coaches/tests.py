from datetime import timedelta

import jdatetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CoachApplication, CoachInvite, CoachProfile, CoachStudent


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


def _make_user(username, **extra):
	return get_user_model().objects.create_user(
		username=username,
		password='Safe-Training-Password-914!',
		**extra,
	)


def _make_profile(user, display_name='مربی کد'):
	application = CoachApplication(
		user=user,
		coaching_level='Advanced',
		specializations='Taekwondo',
		years_experience=8,
		club_name='باشگاه آزمایشی',
		certificate_details='مدرک مربیگری',
		certificate_document=SimpleUploadedFile('certificate.pdf', b'%PDF-1.4 test'),
		status=CoachApplication.Status.APPROVED,
	)
	application.full_clean()
	application.save()
	profile, _ = CoachProfile.objects.update_or_create(
		application=application,
		defaults={
			'display_name': display_name,
			'biography': 'معرفی آزمایشی',
			'is_published': True,
		},
	)
	return profile, application


class CoachInviteTests(TestCase):
	def setUp(self):
		self.coach_user = _make_user('invite-coach', role=get_user_model().Role.COACH)
		self.profile, self.application = _make_profile(self.coach_user)
		self.addCleanup(self.application.certificate_document.delete, save=False)
		self.student = _make_user('invite-student')
		self.invite = CoachInvite.objects.create(coach=self.profile, code='ABCD2345')

	def test_panel_refuses_a_student_account(self):
		self.client.force_login(self.student)

		response = self.client.get(reverse('coach_students:list'))

		self.assertEqual(response.status_code, 403)

	def test_panel_renders_and_lists_the_codes(self):
		self.client.force_login(self.coach_user)

		response = self.client.get(reverse('coach_students:list'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'هنرجوهای من')
		self.assertContains(response, 'ABCD2345')

	def test_coach_creates_a_code_that_belongs_to_their_profile(self):
		self.client.force_login(self.coach_user)

		response = self.client.post(reverse('coach_students:list'), {
			'label': 'کلاس شنبه‌ها',
			'max_uses': 15,
		})

		self.assertRedirects(response, reverse('coach_students:list'))
		invite = CoachInvite.objects.exclude(pk=self.invite.pk).get()
		self.assertEqual(invite.coach, self.profile)
		self.assertEqual(invite.label, 'کلاس شنبه‌ها')
		self.assertEqual(invite.max_uses, 15)
		self.assertEqual(len(invite.code), 8)
		for character in 'IO01':
			self.assertNotIn(character, invite.code)

	def test_toggle_flips_the_code_and_hides_other_coaches_codes(self):
		self.client.force_login(self.coach_user)
		url = reverse('coach_students:toggle_invite', args=[self.invite.pk])

		response = self.client.post(url)

		self.assertRedirects(response, reverse('coach_students:list'))
		self.invite.refresh_from_db()
		self.assertFalse(self.invite.is_active)

		other_user = _make_user('other-coach', role=get_user_model().Role.COACH)
		_, other_application = _make_profile(other_user, 'مربی دیگر')
		self.addCleanup(other_application.certificate_document.delete, save=False)
		self.client.force_login(other_user)

		self.assertEqual(self.client.post(url).status_code, 404)

	def test_join_page_renders_and_unknown_code_is_404(self):
		self.client.force_login(self.student)

		response = self.client.get(reverse('coaches:join_coach', args=[self.invite.code]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.profile.display_name)
		self.assertContains(response, self.invite.code)

		self.assertEqual(
			self.client.get(reverse('coaches:join_coach', args=['NOPE9999'])).status_code,
			404,
		)

	def test_redeeming_a_code_attaches_the_student_once(self):
		self.client.force_login(self.student)
		url = reverse('coaches:join_coach', args=[self.invite.code])

		response = self.client.post(url)
		self.assertRedirects(response, reverse('club:coach_detail', args=[self.profile.pk]))
		second = self.client.post(url)

		self.assertRedirects(second, reverse('club:coach_detail', args=[self.profile.pk]))
		self.assertEqual(CoachStudent.objects.filter(student=self.student).count(), 1)
		self.invite.refresh_from_db()
		self.assertEqual(self.invite.uses, 1)

		self.assertContains(
			self.client.get(url),
			'شما از قبل در فهرست هنرجویان این مربی هستید.',
		)

	def test_codes_are_found_case_insensitively(self):
		self.client.force_login(self.student)

		response = self.client.post(reverse('coaches:join_coach', args=['abcd2345']))

		self.assertRedirects(response, reverse('club:coach_detail', args=[self.profile.pk]))
		self.assertTrue(CoachStudent.objects.filter(coach=self.profile, student=self.student).exists())

	def test_disabled_code_is_refused(self):
		self.invite.is_active = False
		self.invite.save(update_fields=['is_active'])
		self.client.force_login(self.student)

		response = self.client.post(reverse('coaches:join_coach', args=[self.invite.code]))

		self.assertRedirects(response, reverse('coaches:join_coach', args=[self.invite.code]))
		self.assertFalse(CoachStudent.objects.exists())

	def test_expired_code_is_refused(self):
		self.invite.expires_at = timezone.now() - timedelta(days=1)
		self.invite.save(update_fields=['expires_at'])
		self.client.force_login(self.student)

		response = self.client.post(reverse('coaches:join_coach', args=[self.invite.code]))

		self.assertRedirects(response, reverse('coaches:join_coach', args=[self.invite.code]))
		self.assertFalse(CoachStudent.objects.exists())

	def test_exhausted_code_is_refused(self):
		self.invite.max_uses = 1
		self.invite.uses = 1
		self.invite.save(update_fields=['max_uses', 'uses'])
		self.client.force_login(self.student)

		response = self.client.post(reverse('coaches:join_coach', args=[self.invite.code]))

		self.assertRedirects(response, reverse('coaches:join_coach', args=[self.invite.code]))
		self.assertFalse(CoachStudent.objects.exists())

	def test_a_coach_cannot_join_their_own_list(self):
		self.client.force_login(self.coach_user)

		response = self.client.post(reverse('coaches:join_coach', args=[self.invite.code]))

		self.assertRedirects(response, reverse('coaches:join_coach', args=[self.invite.code]))
		self.assertFalse(CoachStudent.objects.exists())


class CoachHubTests(TestCase):
	def setUp(self):
		self.coach_user = _make_user('hub-coach', role=get_user_model().Role.COACH)
		self.client.force_login(self.coach_user)

	def make_application(self, status, reason=''):
		application = CoachApplication(
			user=self.coach_user,
			coaching_level='Advanced',
			specializations='Taekwondo',
			years_experience=5,
			club_name='باشگاه آزمایشی',
			certificate_details='مدرک مربیگری',
			certificate_document=SimpleUploadedFile('hub.pdf', b'%PDF-1.4 hub'),
			status=status,
			rejection_reason=reason,
		)
		application.full_clean()
		application.save()
		self.addCleanup(application.certificate_document.delete, save=False)
		return application

	def approve(self):
		application = self.make_application(CoachApplication.Status.PENDING_REVIEW)
		application.status = CoachApplication.Status.APPROVED
		application.save()
		return application

	def test_account_offers_the_form_before_any_request(self):
		response = self.client.get(reverse('account'))

		self.assertContains(response, 'ثبت درخواست مربیگری')
		self.assertContains(response, 'ثبت نشده')

	def test_pending_status_is_visible_without_opening_the_status_page(self):
		self.make_application(CoachApplication.Status.PENDING_REVIEW)

		response = self.client.get(reverse('account'))

		self.assertContains(response, 'در انتظار بررسی')
		self.assertNotContains(response, 'ثبت درخواست مربیگری')

	def test_rejected_request_shows_the_reason_and_a_resubmit_link(self):
		self.make_application(CoachApplication.Status.REJECTED, 'مدرک ناخوانا بود.')

		response = self.client.get(reverse('account'))

		self.assertContains(response, 'مدرک ناخوانا بود.')
		self.assertContains(response, 'ویرایش و ارسال دوباره')

	def test_rejected_request_can_be_edited_and_resent(self):
		application = self.make_application(CoachApplication.Status.REJECTED, 'ناقص بود.')
		original_submitted_at = application.submitted_at

		response = self.client.get(reverse('coaches:apply'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'ارسال دوباره')

		response = self.client.post(reverse('coaches:apply'), {
			'coaching_level': 'Advanced',
			'specializations': 'Kata',
			'years_experience': 9,
			'club_name': 'باشگاه تازه',
			'certificate_details': 'مدرک کامل',
		})

		self.assertRedirects(response, reverse('coaches:application_status'))
		application.refresh_from_db()
		self.assertEqual(application.status, CoachApplication.Status.PENDING_REVIEW)
		self.assertEqual(application.rejection_reason, '')
		self.assertIsNone(application.reviewed_at)
		self.assertEqual(application.specializations, 'Kata')
		self.assertEqual(application.club_name, 'باشگاه تازه')
		self.assertGreater(application.submitted_at, original_submitted_at)
		self.assertEqual(CoachApplication.objects.filter(user=self.coach_user).count(), 1)

	def test_pending_request_cannot_be_edited(self):
		self.make_application(CoachApplication.Status.PENDING_REVIEW)

		response = self.client.get(reverse('coaches:apply'))

		self.assertRedirects(response, reverse('coaches:application_status'))

	def test_approved_request_cannot_be_edited(self):
		self.approve()

		response = self.client.get(reverse('coaches:apply'))

		self.assertRedirects(response, reverse('coaches:application_status'))

	def test_approval_creates_an_unpublished_profile(self):
		application = self.approve()

		profile = CoachProfile.objects.get(application=application)

		self.assertFalse(profile.is_published)

	def test_approved_account_lists_the_panels(self):
		self.approve()

		response = self.client.get(reverse('account'))

		self.assertContains(response, reverse('coach_panel:course_list'))
		self.assertContains(response, reverse('coach_students:list'))
		self.assertContains(response, reverse('coaches:portfolio'))

	def test_portfolio_renders_and_saves_without_publishing(self):
		application = self.approve()

		response = self.client.get(reverse('coaches:portfolio'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'پروفایل عمومی من')

		response = self.client.post(reverse('coaches:portfolio'), {
			'display_name': 'مربی هاب',
			'headline': 'مربی کاتا',
			'biography': 'معرفی تازه',
			'belt': 'دان ۳',
			'club': 'باشگاه مرکزی',
		})

		self.assertRedirects(response, reverse('coaches:portfolio'))
		profile = CoachProfile.objects.get(application=application)
		self.assertEqual(profile.display_name, 'مربی هاب')
		self.assertEqual(profile.belt, 'دان ۳')
		self.assertFalse(profile.is_published)

	def test_portfolio_refuses_a_student(self):
		self.client.force_login(_make_user('portfolio-student'))

		self.assertEqual(self.client.get(reverse('coaches:portfolio')).status_code, 403)

	def test_portfolio_redirects_a_pending_coach_to_the_status_page(self):
		self.make_application(CoachApplication.Status.PENDING_REVIEW)

		response = self.client.get(reverse('coaches:portfolio'))

		self.assertRedirects(response, reverse('coaches:application_status'))

	def test_status_page_offers_a_resubmit_button_when_rejected(self):
		self.make_application(CoachApplication.Status.REJECTED, 'مدرک ناخوانا بود.')

		response = self.client.get(reverse('coaches:application_status'))

		self.assertContains(response, 'مدرک ناخوانا بود.')
		self.assertContains(response, 'ویرایش و ارسال دوباره')

