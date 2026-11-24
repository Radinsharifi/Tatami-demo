import io
import json
from datetime import time
from decimal import Decimal
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

# Test-only import: the roster panel links coach accounts, so the fixtures
# need real portfolios. Production code in `gyms` never imports `coaches`.
from coaches.models import CoachPortfolio
from coaches.templatetags.persian import persian_digits

from .geocoding import GeocodingError, geocode, reverse_geocode
from .models import Gym, GymCoachPlaceholder, GymWorkingHour
from .services import create_gym, ensure_working_hours

VALID_GYM = {
	'name': 'باشگاه تاتامی',
	'phone': '02112345678',
	'address': 'تهران، خیابان آزادی، پلاک ۱۲',
	'latitude': '35.721900',
	'longitude': '51.389000',
}


def make_user(phone, role='student'):
	return get_user_model().objects.create_user(
		phone=phone,
		role=role,
		is_profile_complete=True,
	)


def make_coach(phone):
	user = make_user(phone, role=get_user_model().Role.COACH)
	portfolio = CoachPortfolio(
		user=user,
		display_name='مربی آزمایشی',
		status=CoachPortfolio.Status.APPROVED,
	)
	portfolio.full_clean()
	portfolio.save()
	return portfolio


class GymCreationTests(TestCase):
	"""Flow one: the owner registers with OTP and creates the club (CLUB-01…05, 08–11)."""

	def setUp(self):
		self.owner = make_user('09120000020', role=get_user_model().Role.GYM)
		self.student = make_user('09120000021')

	def test_owner_sees_the_creation_form(self):
		self.client.force_login(self.owner)

		response = self.client.get(reverse('gyms:create'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'ساخت باشگاه')
		self.assertContains(response, 'name="phone"')
		self.assertContains(response, 'name="latitude"')

	def test_student_cannot_open_the_creation_form(self):
		self.client.force_login(self.student)

		response = self.client.get(reverse('gyms:create'))

		self.assertEqual(response.status_code, 403)

	def test_creating_a_club_links_the_owner_and_builds_the_structure(self):
		self.client.force_login(self.owner)

		response = self.client.post(reverse('gyms:create'), VALID_GYM)

		self.assertRedirects(response, reverse('gyms:panel'))
		gym = Gym.objects.get()
		self.assertEqual(gym.owner, self.owner)
		self.assertEqual(gym.created_by, self.owner)
		self.assertEqual(gym.status, Gym.Status.PENDING)
		self.assertEqual(gym.working_hours.count(), 7)

	def test_missing_address_is_rejected(self):
		self.client.force_login(self.owner)
		payload = {**VALID_GYM, 'address': ''}

		response = self.client.post(reverse('gyms:create'), payload)

		self.assertEqual(response.status_code, 200)
		# Check the form error itself, not Django's translated wording:
		# the fa catalog says «این فیلد لازم است.», and hard-coding it made
		# this test fail for a wording mismatch, not a real bug.
		self.assertIn('address', response.context['form'].errors)
		self.assertContains(response, 'field-error')
		self.assertFalse(Gym.objects.exists())

	def test_invalid_phone_is_rejected(self):
		self.client.force_login(self.owner)
		payload = {**VALID_GYM, 'phone': '12345'}

		response = self.client.post(reverse('gyms:create'), payload)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'شمارهٔ باشگاه')
		self.assertFalse(Gym.objects.exists())

	def test_persian_digits_in_phone_are_normalized(self):
		self.client.force_login(self.owner)
		payload = {**VALID_GYM, 'phone': '۰۲۱۱۲۳۴۵۶۷۸'}

		self.client.post(reverse('gyms:create'), payload)

		self.assertEqual(Gym.objects.get().phone, '02112345678')

	def test_coordinates_are_stored_as_numbers(self):
		self.client.force_login(self.owner)

		self.client.post(reverse('gyms:create'), VALID_GYM)

		gym = Gym.objects.get()
		self.assertEqual(gym.latitude, Decimal('35.721900'))
		self.assertEqual(gym.longitude, Decimal('51.389000'))

	def test_out_of_range_coordinates_are_rejected(self):
		self.client.force_login(self.owner)
		payload = {**VALID_GYM, 'latitude': '95.0'}

		response = self.client.post(reverse('gyms:create'), payload)

		self.assertEqual(response.status_code, 200)
		self.assertIn('latitude', response.context['form'].errors)
		self.assertFalse(Gym.objects.exists())

	def test_creating_twice_keeps_a_single_club(self):
		self.client.force_login(self.owner)
		self.client.post(reverse('gyms:create'), VALID_GYM)

		response = self.client.get(reverse('gyms:create'))

		self.assertRedirects(response, reverse('gyms:panel'))
		self.assertEqual(Gym.objects.count(), 1)


class GymPanelTests(TestCase):
	"""The dashboard renders every section, empty or not (CLUB-03, 04, 11)."""

	def setUp(self):
		self.owner = make_user('09120000022', role=get_user_model().Role.GYM)
		self.gym = create_gym(
			owner=self.owner,
			created_by=self.owner,
			status=Gym.Status.PENDING,
			**VALID_GYM,
		)
		self.student = make_user('09120000023')

	def test_panel_renders_every_section_with_empty_lists(self):
		self.client.force_login(self.owner)

		response = self.client.get(reverse('gyms:panel'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'اطلاعات باشگاه')
		self.assertContains(response, 'مربیان')
		self.assertContains(response, 'دانش‌آموزان')
		self.assertContains(response, 'ساعت کاری')
		self.assertContains(response, 'موقعیت')
		# Empty coach and student lists must render, not break, the panel.
		self.assertContains(response, 'هنوز مربی‌ای به حساب کاربری متصل نشده است')
		self.assertContains(response, 'هنوز دانش‌آموزی ثبت نشده است')

	def test_panel_shows_the_weekly_hours(self):
		self.client.force_login(self.owner)

		response = self.client.get(reverse('gyms:panel'))

		self.assertContains(response, 'شنبه')
		self.assertContains(response, 'جمعه')
		self.assertContains(response, 'تعطیل')
		self.assertContains(response, '۰۹:۰۰')

	def test_student_cannot_open_the_panel(self):
		self.client.force_login(self.student)

		response = self.client.get(reverse('gyms:panel'))

		self.assertEqual(response.status_code, 403)

	def test_gym_role_without_a_club_is_sent_to_create(self):
		rookie = make_user('09120000024', role=get_user_model().Role.GYM)
		self.client.force_login(rookie)

		response = self.client.get(reverse('gyms:panel'))

		self.assertRedirects(response, reverse('gyms:create'))


class CoachRosterTests(TestCase):
	"""Both roster kinds: linked accounts and text placeholders for coaches
	who have not joined the app yet."""

	def setUp(self):
		self.owner = make_user('09120000025', role=get_user_model().Role.GYM)
		self.gym = create_gym(
			owner=self.owner,
			created_by=self.owner,
			status=Gym.Status.PENDING,
			**VALID_GYM,
		)
		self.coach = make_coach('09120000026')
		self.client.force_login(self.owner)

	def test_placeholder_without_an_account_is_added_and_listed(self):
		response = self.client.post(
			reverse('gyms:coach_placeholder_add'),
			{'name': 'مربی مهمان', 'phone': '09120000027'},
		)

		self.assertRedirects(response, reverse('gyms:panel'))
		placeholder = GymCoachPlaceholder.objects.get()
		self.assertEqual(placeholder.gym, self.gym)
		self.assertEqual(placeholder.phone, '09120000027')
		self.assertContains(self.client.get(reverse('gyms:panel')), 'مربی مهمان')

	def test_placeholder_without_a_phone_is_allowed(self):
		self.client.post(reverse('gyms:coach_placeholder_add'), {'name': 'مربی بی‌شماره'})

		self.assertEqual(GymCoachPlaceholder.objects.count(), 1)

	def test_duplicate_placeholder_phone_is_rejected(self):
		payload = {'name': 'مربی اول', 'phone': '09120000028'}
		self.client.post(reverse('gyms:coach_placeholder_add'), payload)

		response = self.client.post(
			reverse('gyms:coach_placeholder_add'),
			{'name': 'مربی دوم', 'phone': '09120000028'},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'در فهرست باشگاه ثبت شده است')
		self.assertEqual(GymCoachPlaceholder.objects.count(), 1)

	def test_placeholder_phone_is_normalized(self):
		self.client.post(
			reverse('gyms:coach_placeholder_add'),
			{'name': 'مربی فارسی', 'phone': '۰۹۱۲۰۰۰۰۰۲۹'},
		)

		self.assertEqual(GymCoachPlaceholder.objects.get().phone, '09120000029')

	def test_placeholder_is_removed(self):
		self.client.post(
			reverse('gyms:coach_placeholder_add'),
			{'name': 'مربی حذف‌شدنی', 'phone': '09120000030'},
		)
		placeholder = GymCoachPlaceholder.objects.get()

		response = self.client.post(reverse('gyms:coach_placeholder_remove', args=[placeholder.pk]))

		self.assertRedirects(response, reverse('gyms:panel'))
		self.assertFalse(GymCoachPlaceholder.objects.exists())

	def test_registered_coach_is_linked_by_phone(self):
		response = self.client.post(reverse('gyms:coach_link'), {'phone': '09120000026'})

		self.assertRedirects(response, reverse('gyms:panel'))
		self.coach.refresh_from_db()
		self.assertEqual(self.coach.gym, self.gym)
		self.assertContains(self.client.get(reverse('gyms:panel')), 'مربی آزمایشی')

	def test_unknown_phone_is_rejected_with_a_hint(self):
		response = self.client.post(reverse('gyms:coach_link'), {'phone': '09129999999'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'ثبت نشده است')
		self.coach.refresh_from_db()
		self.assertIsNone(self.coach.gym)

	def test_coach_of_another_club_cannot_be_linked(self):
		other_owner = make_user('09120000031', role=get_user_model().Role.GYM)
		other_gym = create_gym(
			owner=other_owner,
			created_by=other_owner,
			status=Gym.Status.PENDING,
			**{**VALID_GYM, 'name': 'باشگاه دیگر'},
		)
		self.coach.gym = other_gym
		self.coach.save(update_fields=['gym'])

		response = self.client.post(reverse('gyms:coach_link'), {'phone': '09120000026'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'باشگاه دیگری متصل است')
		self.coach.refresh_from_db()
		self.assertEqual(self.coach.gym, other_gym)

	def test_linking_the_same_coach_twice_stays_idempotent(self):
		self.client.post(reverse('gyms:coach_link'), {'phone': '09120000026'})

		response = self.client.post(reverse('gyms:coach_link'), {'phone': '09120000026'})

		self.assertRedirects(response, reverse('gyms:panel'))
		self.coach.refresh_from_db()
		self.assertEqual(self.coach.gym, self.gym)

	def test_linked_coach_is_unlinked(self):
		self.client.post(reverse('gyms:coach_link'), {'phone': '09120000026'})

		response = self.client.post(reverse('gyms:coach_unlink', args=[self.coach.pk]))

		self.assertRedirects(response, reverse('gyms:panel'))
		self.coach.refresh_from_db()
		self.assertIsNone(self.coach.gym)

	def test_student_cannot_touch_the_roster(self):
		student = make_user('09120000032')
		self.client.force_login(student)

		response = self.client.post(
			reverse('gyms:coach_placeholder_add'),
			{'name': 'نفوذی', 'phone': '09120000033'},
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(GymCoachPlaceholder.objects.exists())


class WorkingHoursTests(TestCase):
	def test_ensure_working_hours_is_idempotent(self):
		gym = Gym.objects.create(**VALID_GYM)

		ensure_working_hours(gym)
		ensure_working_hours(gym)

		self.assertEqual(gym.working_hours.count(), 7)

	def test_friday_starts_closed_and_weekdays_have_times(self):
		gym = create_gym(**VALID_GYM)

		friday = gym.working_hours.get(day=GymWorkingHour.Day.FRIDAY)
		saturday = gym.working_hours.get(day=GymWorkingHour.Day.SATURDAY)
		self.assertTrue(friday.is_closed)
		self.assertIsNone(friday.opens)
		self.assertEqual(saturday.opens, time(9, 0))
		self.assertEqual(saturday.closes, time(22, 0))

	def test_open_day_requires_start_and_end_times(self):
		gym = create_gym(**VALID_GYM)
		hour = GymWorkingHour(gym=gym, day=GymWorkingHour.Day.SUNDAY, is_closed=False)

		with self.assertRaises(ValidationError) as caught:
			hour.full_clean()

		self.assertIn('ساعت شروع و پایان', str(caught.exception))


class GymAdminTests(TestCase):
	"""Flow two: the admin's «مدیریت باشگاه‌ها» (CLUB-06, 07, 11, 12)."""

	def setUp(self):
		self.admin = get_user_model().objects.create_superuser(
			phone='09120000090',
			password='admin-password-123',
		)
		self.client.force_login(self.admin)

	def test_admin_list_shows_registered_clubs(self):
		create_gym(status=Gym.Status.ACTIVE, **VALID_GYM)

		response = self.client.get(reverse('admin:gyms_gym_changelist'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'باشگاه تاتامی')

	def test_admin_add_creates_an_active_club_with_default_hours(self):
		response = self.client.post(reverse('admin:gyms_gym_add'), {
			'name': 'باشگاه اداری',
			'phone': '02188776655',
			'address': 'تهران، خیابان ولیعصر',
			'latitude': '35.710000',
			'longitude': '51.420000',
			'status': 'active',
			'owner': '',
			'working_hours-TOTAL_FORMS': '0',
			'working_hours-INITIAL_FORMS': '0',
			'working_hours-MIN_NUM_FORMS': '0',
			'working_hours-MAX_NUM_FORMS': '1000',
		})

		self.assertEqual(response.status_code, 302)
		gym = Gym.objects.get(name='باشگاه اداری')
		self.assertEqual(gym.status, Gym.Status.ACTIVE)
		self.assertEqual(gym.created_by, self.admin)
		self.assertIsNone(gym.owner)
		self.assertEqual(gym.working_hours.count(), 7)

	def test_admin_add_saves_inline_hours_and_fills_the_rest(self):
		response = self.client.post(reverse('admin:gyms_gym_add'), {
			'name': 'باشگاه ساعت‌دار',
			'phone': '02111223344',
			'address': 'تهران',
			'latitude': '35.700000',
			'longitude': '51.400000',
			'status': 'active',
			'owner': '',
			'working_hours-TOTAL_FORMS': '1',
			'working_hours-INITIAL_FORMS': '0',
			'working_hours-MIN_NUM_FORMS': '0',
			'working_hours-MAX_NUM_FORMS': '1000',
			'working_hours-0-day': '0',
			'working_hours-0-opens': '08:00',
			'working_hours-0-closes': '20:00',
			'working_hours-0-is_closed': '',
		})

		self.assertEqual(response.status_code, 302)
		gym = Gym.objects.get(name='باشگاه ساعت‌دار')
		self.assertEqual(gym.working_hours.count(), 7)
		saturday = gym.working_hours.get(day=GymWorkingHour.Day.SATURDAY)
		self.assertEqual(saturday.opens, time(8, 0))
		self.assertEqual(saturday.closes, time(20, 0))
		self.assertTrue(gym.working_hours.get(day=GymWorkingHour.Day.FRIDAY).is_closed)

	def test_admin_add_rejects_an_invalid_phone(self):
		response = self.client.post(reverse('admin:gyms_gym_add'), {
			'name': 'باشگاه خراب',
			'phone': '123',
			'address': 'تهران',
			'latitude': '35.700000',
			'longitude': '51.400000',
			'status': 'active',
			'owner': '',
			'working_hours-TOTAL_FORMS': '0',
			'working_hours-INITIAL_FORMS': '0',
			'working_hours-MIN_NUM_FORMS': '0',
			'working_hours-MAX_NUM_FORMS': '1000',
		})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'شمارهٔ باشگاه')
		self.assertFalse(Gym.objects.exists())


class GymPublicPagesTests(TestCase):
	"""The public directory and detail pages — only `active` clubs show up,
	flipped by the team in Django Admin."""

	def setUp(self):
		self.owner = make_user('09120000036', role=get_user_model().Role.GYM)
		self.active = create_gym(
			owner=self.owner,
			created_by=self.owner,
			status=Gym.Status.ACTIVE,
			**VALID_GYM,
		)
		self.pending = create_gym(
			status=Gym.Status.PENDING,
			**{**VALID_GYM, 'name': 'باشگاه در انتظار', 'phone': '02199887766'},
		)

	def test_directory_lists_only_active_clubs(self):
		response = self.client.get(reverse('gyms:directory'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'باشگاه تاتامی')
		self.assertContains(response, reverse('gyms:detail', args=[self.active.pk]))
		self.assertNotContains(response, 'باشگاه در انتظار')

	def test_directory_shows_an_empty_state_when_no_club_is_active(self):
		Gym.objects.all().delete()

		response = self.client.get(reverse('gyms:directory'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'هنوز باشگاه فعالی ثبت نشده است')

	def test_detail_shows_all_the_club_data(self):
		response = self.client.get(reverse('gyms:detail', args=[self.active.pk]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'باشگاه تاتامی')
		self.assertContains(response, VALID_GYM['address'])
		self.assertContains(response, persian_digits(VALID_GYM['phone']))
		self.assertContains(response, persian_digits(VALID_GYM['latitude']))
		self.assertContains(response, 'شنبه')
		self.assertContains(response, 'تعطیل')
		self.assertContains(response, 'اطلاعات تماس')

	def test_pending_club_has_no_public_page(self):
		response = self.client.get(reverse('gyms:detail', args=[self.pending.pk]))

		self.assertEqual(response.status_code, 404)

	def test_detail_lists_linked_and_placeholder_coaches(self):
		coach = make_coach('09120000037')
		coach.is_published = True
		coach.gym = self.active
		coach.save(update_fields=['is_published', 'gym', 'updated_at'])
		GymCoachPlaceholder.objects.create(
			gym=self.active, name='مربی مهمان', phone='09120000038',
		)

		response = self.client.get(reverse('gyms:detail', args=[self.active.pk]))

		self.assertContains(response, 'مربی آزمایشی')
		self.assertContains(response, 'مربی مهمان')
		# Roster phone numbers are never shown on the public page.
		self.assertNotContains(response, '09120000038')

	def test_detail_hides_linked_coaches_that_are_not_published(self):
		coach = make_coach('09120000039')
		coach.gym = self.active
		coach.save(update_fields=['gym', 'updated_at'])

		response = self.client.get(reverse('gyms:detail', args=[self.active.pk]))

		self.assertContains(response, 'هنوز مربی‌ای برای این باشگاه معرفی نشده است')
		self.assertNotContains(response, 'مربی آزمایشی')


class AccountHubTests(TestCase):
	"""The guest chooser and the gym role's section on `/account/`."""

	def test_guest_chooser_offers_the_gym_path(self):
		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'role=gym')
		self.assertContains(response, 'باشگاهت را ثبت کن')

	def test_gym_owner_sees_the_panel_link(self):
		owner = make_user('09120000034', role=get_user_model().Role.GYM)
		create_gym(owner=owner, created_by=owner, status=Gym.Status.PENDING, **VALID_GYM)
		self.client.force_login(owner)

		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'پنل باشگاه')
		self.assertContains(response, reverse('gyms:panel'))

	def test_gym_user_without_a_club_sees_the_create_button(self):
		rookie = make_user('09120000035', role=get_user_model().Role.GYM)
		self.client.force_login(rookie)

		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, reverse('gyms:create'))


class GeocodingTests(TestCase):
	"""The server-side Neshan client (PRD item 6, geolocation API only).

	Network is always mocked: no test may reach the real service, and the
	Service Key travels only in the `Api-Key` header — never in the URL.
	"""

	def test_missing_key_fails_clearly_instead_of_calling_the_network(self):
		with override_settings(NESHAN_API_KEY=''), patch('gyms.geocoding.urlopen') as network:
			with self.assertRaises(GeocodingError) as caught:
				geocode('تهران، خیابان آزادی')

		self.assertIn('NESHAN_API_KEY', str(caught.exception))
		network.assert_not_called()

	def test_empty_address_is_rejected_before_any_request(self):
		with patch('gyms.geocoding.urlopen') as network:
			with self.assertRaises(GeocodingError) as caught:
				geocode('   ')

		self.assertIn('آدرس خالی', str(caught.exception))
		network.assert_not_called()

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_geocode_returns_storable_coordinates(self, network):
		network.return_value.read.return_value = json.dumps({
			'status': 'OK',
			'location': {'x': 51.389000123, 'y': 35.721900456},
		}).encode()

		result = geocode('تهران، خیابان آزادی')

		self.assertEqual(result['lat'], Decimal('35.721900'))
		self.assertEqual(result['lng'], Decimal('51.389000'))
		request = network.call_args.args[0]
		self.assertIn('/v6/geocoding', request.full_url)
		self.assertIn('address=', request.full_url)
		self.assertGreater(network.call_args.kwargs['timeout'], 0)
		# The key rides in the header only, so it can't leak via URLs/logs.
		self.assertTrue(any(k.lower() == 'api-key' for k in request.headers))

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_reverse_returns_the_location_payload(self, network):
		payload = {
			'status': 'OK',
			'formatted_address': 'تهران، دکتر فاطمی، حجاب',
			'city': 'تهران',
			'state': 'استان تهران',
		}
		network.return_value.read.return_value = json.dumps(payload).encode()

		result = reverse_geocode('35.721900', '51.389000')

		self.assertEqual(result['formatted_address'], 'تهران، دکتر فاطمی، حجاب')
		self.assertEqual(result['city'], 'تهران')
		self.assertIn('/v5/reverse', network.call_args.args[0].full_url)

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_service_error_codes_surface_by_name(self, network):
		network.side_effect = HTTPError(
			'https://api.neshan.org/v6/geocoding',
			481,
			'LimitExceeded',
			hdrs=None,
			fp=io.BytesIO(b'{"status": "LimitExceeded"}'),
		)

		with self.assertRaises(GeocodingError) as caught:
			geocode('تهران')

		self.assertIn('LimitExceeded', str(caught.exception))
		self.assertIn('481', str(caught.exception))

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_non_ok_status_in_a_200_response_is_an_error(self, network):
		network.return_value.read.return_value = b'{"status": "NOT_FOUND"}'

		with self.assertRaises(GeocodingError) as caught:
			geocode('آدرس ناشناس')

		self.assertIn('NOT_FOUND', str(caught.exception))

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_unparsable_body_is_an_error(self, network):
		network.return_value.read.return_value = b'<html>gateway</html>'

		with self.assertRaises(GeocodingError) as caught:
			geocode('تهران')

		self.assertIn('نامعتبر', str(caught.exception))

	@override_settings(NESHAN_API_KEY='service-key')
	@patch('gyms.geocoding.urlopen')
	def test_unreachable_service_is_an_error(self, network):
		network.side_effect = URLError('connection refused')

		with self.assertRaises(GeocodingError) as caught:
			reverse_geocode('35.721900', '51.389000')

		self.assertIn('ممکن نشد', str(caught.exception))
