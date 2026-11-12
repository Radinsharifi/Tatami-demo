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
		messages.info(request, 'پروفایل عمومی شما هنوز ساخته نشده است.')
		return None, redirect('coaches:application_status')
	return profile, None
