from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.contrib.auth.models import Group
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
import jdatetime

from .models import OTPCode, SignupLead
from .phone import normalize_iranian_phone
from .sms import FakeSMSBackend


class UserRoleTests(TestCase):
	def test_new_user_defaults_to_student(self):
		user = get_user_model().objects.create_user(username='new-student', password='test-password')
		user.refresh_from_db()

		self.assertEqual(user.role, get_user_model().Role.STUDENT)
		self.assertIsInstance(user.date_joined, jdatetime.datetime)

	def test_coach_role_can_be_assigned(self):
		user = get_user_model().objects.create_user(
			username='new-coach',
			password='test-password',
			role=get_user_model().Role.COACH,
		)

		self.assertEqual(user.role, get_user_model().Role.COACH)


@override_settings(SMS_BACKEND='accounts.sms.FakeSMSBackend')
class AuthenticationFlowTests(TestCase):
	phone = '09123456789'

	def setUp(self):
		cache.clear()
		FakeSMSBackend.messages.clear()

	def request_code(self, phone=None, role='student', next_url=''):
		return self.client.post(reverse('phone_auth:login'), {
			'phone': phone or self.phone,
			'role': role,
			'next_url': next_url,
		})

	def verify_latest_code(self):
		phone, code = FakeSMSBackend.messages[-1]
		return self.client.post(reverse('phone_auth:verify_otp'), {'code': code})

	def test_phone_normalization_accepts_iranian_dialing_formats(self):
		self.assertEqual(normalize_iranian_phone('+98 912 345 6789'), self.phone)
		self.assertEqual(normalize_iranian_phone('۰۹۱۲۳۴۵۶۷۸۹'), self.phone)

	def test_login_page_renders_and_keeps_a_safe_next_target(self):
		response = self.client.get(reverse('phone_auth:login'), {'next': '/store/cart/'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="next_url"')
		self.assertContains(response, 'value="/store/cart/"')

	def test_new_phone_is_created_only_after_valid_otp(self):
		response = self.request_code(role='coach')
		self.assertRedirects(response, reverse('phone_auth:verify_otp'))
		self.assertFalse(get_user_model().objects.filter(phone=self.phone).exists())

		otp = OTPCode.objects.get(phone=self.phone)
		code_phone, code = FakeSMSBackend.messages[-1]
		self.assertEqual(code_phone, self.phone)
		self.assertNotEqual(otp.code_hash, code)
		self.assertTrue(otp.verify(code))

		response = self.verify_latest_code()
		self.assertRedirects(response, reverse('phone_auth:complete_profile'))
		user = get_user_model().objects.get(phone=self.phone)
		self.assertEqual(user.username, self.phone)
		self.assertEqual(user.role, get_user_model().Role.COACH)
		self.assertFalse(user.has_usable_password())
		self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

	def test_invalid_code_attempts_are_persisted_and_code_is_consumed(self):
		self.request_code()
		otp = OTPCode.objects.get(phone=self.phone)

		for _ in range(5):
			response = self.client.post(reverse('phone_auth:verify_otp'), {'code': '00000'})
			self.assertEqual(response.status_code, 200)

		otp.refresh_from_db()
		self.assertEqual(otp.attempts, 5)
		self.assertTrue(otp.is_used)
		self.assertFalse(get_user_model().objects.filter(phone=self.phone).exists())

	def test_expired_code_is_consumed_without_creating_user(self):
		self.request_code()
		otp = OTPCode.objects.get(phone=self.phone)
		otp.expires_at = timezone.now() - timedelta(seconds=1)
		otp.save(update_fields=['expires_at'])

		self.verify_latest_code()

		otp.refresh_from_db()
		self.assertTrue(otp.is_used)
		self.assertFalse(get_user_model().objects.filter(phone=self.phone).exists())

	def test_phone_cooldown_limits_resend(self):
		self.request_code()
		response = self.client.post(reverse('phone_auth:send_otp'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(OTPCode.objects.filter(phone=self.phone).count(), 1)

	def test_profile_completion_preserves_safe_next_destination(self):
		self.request_code(next_url='/store/')
		response = self.verify_latest_code()
		self.assertRedirects(response, reverse('phone_auth:complete_profile'))

		response = self.client.post(reverse('phone_auth:complete_profile'), {
			'name': 'هنرجوی آزمایشی',
			'city': 'کرج',
			'role': 'student',
		})

		self.assertRedirects(response, '/store/')
		user = get_user_model().objects.get(phone=self.phone)
		self.assertTrue(user.is_profile_complete)
		self.assertEqual(user.city, 'کرج')

	def test_existing_phone_account_keeps_its_role(self):
		user = get_user_model().objects.create_user(
			phone=self.phone,
			role=get_user_model().Role.STUDENT,
			is_profile_complete=True,
		)
		self.request_code(role='coach')

		response = self.verify_latest_code()

		self.assertRedirects(response, reverse('account'))
		user.refresh_from_db()
		self.assertEqual(user.pk, int(self.client.session['_auth_user_id']))
		self.assertEqual(user.role, get_user_model().Role.STUDENT)

	def test_legacy_phone_less_staff_can_still_authenticate_by_username(self):
		staff = get_user_model().objects.create_user(
			username='legacy-staff',
			password='Existing-Admin-Password-914!',
			is_staff=True,
		)

		self.assertIsNone(staff.phone)
		self.assertEqual(
			authenticate(username='legacy-staff', password='Existing-Admin-Password-914!'),
			staff,
		)

	def test_logout_remains_post_only_and_clears_session(self):
		self.request_code()
		self.verify_latest_code()
		response = self.client.post('/accounts/logout/')

		self.assertRedirects(response, '/')
		self.assertNotIn('_auth_user_id', self.client.session)


class CoachSignupLeadTests(TestCase):
	def test_new_coach_account_creates_one_open_lead(self):
		user = get_user_model().objects.create_user(
			phone='09120000001',
			is_profile_complete=False,
			role=get_user_model().Role.COACH,
		)

		lead = SignupLead.objects.get(user=user)

		self.assertEqual(lead.status, SignupLead.Status.NEW)
		self.assertEqual(lead.assigned_to, None)
		self.assertEqual(SignupLead.objects.filter(user=user).count(), 1)

	def test_student_account_does_not_create_call_center_lead(self):
		user = get_user_model().objects.create_user(phone='09120000002')

		self.assertFalse(SignupLead.objects.filter(user=user).exists())

	def test_lead_admin_is_hidden_from_non_call_center_user(self):
		staff = get_user_model().objects.create_user(
			username='unassigned-staff',
			password='Existing-Admin-Password-914!',
			is_staff=True,
		)
		self.client.force_login(staff)

		response = self.client.get(reverse('admin:accounts_signuplead_changelist'))

		self.assertEqual(response.status_code, 403)

	def test_call_center_member_can_manage_leads_and_see_new_count(self):
		coach = get_user_model().objects.create_user(
			phone='09120000003',
			role=get_user_model().Role.COACH,
		)
		operator = get_user_model().objects.create_user(
			username='call-agent',
			password='Existing-Admin-Password-914!',
			is_staff=True,
		)
		group, _ = Group.objects.get_or_create(name='call_center')
		operator.groups.add(group)
		self.client.force_login(operator)

		response = self.client.get(reverse('admin:accounts_signuplead_changelist'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'سرنخ‌های جدید مربی: 1')
		self.assertContains(response, coach.phone)
