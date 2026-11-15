from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.models import User

from .models import CoachApplication, CoachProfile


def coach_profile_or_redirect(request):
	"""The signed-in coach's approved profile, or a redirect response.

	Shared by the course panel and the student panel so both refuse the same
	users for the same reasons: not a coach, no application, not approved, or
	no public profile yet.
	"""
	if request.user.role != User.Role.COACH:
		raise PermissionDenied

	application = getattr(request.user, 'coach_application', None)
	if application is None:
		return None, redirect('coaches:apply')
	if application.status != CoachApplication.Status.APPROVED:
		messages.info(request, 'پنل مربی پس از تأیید درخواست مربیگری فعال می‌شود.')
		return None, redirect('coaches:application_status')

	profile = CoachProfile.objects.filter(application=application).first()
	if profile is None:
		# Legacy approved rows predate the auto-created profile. Create the
		# shell here so the panels never dead-end on "profile not created yet".
		name = (
			application.user.get_full_name()
			or application.user.first_name
			or application.user.phone
			or 'مربی تاتامی پلاس'
		)
		profile = CoachProfile.objects.create(
			application=application,
			display_name=name[:100],
			biography='',
		)
	return profile, None
