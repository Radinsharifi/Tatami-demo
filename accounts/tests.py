from django.contrib.auth import get_user_model
from django.test import TestCase
import jdatetime


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


class AuthenticationFlowTests(TestCase):
	def test_registration_creates_coach_and_starts_session(self):
		response = self.client.post(
			'/accounts/register/',
			{
				'username': 'coach-account',
				'email': 'coach@example.com',
				'role': get_user_model().Role.COACH,
				'password1': 'Safe-Training-Password-914!',
				'password2': 'Safe-Training-Password-914!',
			},
		)

		self.assertRedirects(response, '/account/')
		user = get_user_model().objects.get(username='coach-account')
		self.assertEqual(user.role, get_user_model().Role.COACH)
		self.assertTrue(user.check_password('Safe-Training-Password-914!'))
		self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

	def test_registration_rejects_gym_role(self):
		response = self.client.post(
			'/accounts/register/',
			{
				'username': 'gym-account',
				'role': 'gym',
				'password1': 'Safe-Training-Password-914!',
				'password2': 'Safe-Training-Password-914!',
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(get_user_model().objects.filter(username='gym-account').exists())

	def test_login_honors_next_and_logout_clears_session(self):
		user = get_user_model().objects.create_user(
			username='session-user',
			password='Safe-Training-Password-914!',
		)
		response = self.client.post(
			'/accounts/login/?next=/store/',
			{'username': user.username, 'password': 'Safe-Training-Password-914!', 'next': '/store/'},
		)

		self.assertRedirects(response, '/store/')
		response = self.client.post('/accounts/logout/')

		self.assertRedirects(response, '/')
		self.assertNotIn('_auth_user_id', self.client.session)
