from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.models import User

from .models import Gym


def gym_or_redirect(request):
	"""The signed-in owner's gym, or a redirect response.

	Shared by every panel view so they all refuse the same users for the
	same reasons: not a gym-role account, or no club created yet.
	"""
	if request.user.role != User.Role.GYM:
		raise PermissionDenied

	gym = Gym.objects.filter(owner=request.user).first()
	if gym is None:
		return None, redirect('gyms:create')
	return gym, None
