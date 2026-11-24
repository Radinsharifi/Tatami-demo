from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User

from .access import gym_or_redirect
from .forms import GymCoachPlaceholderForm, GymForm, LinkCoachForm
from .models import Gym
from .services import create_gym


def _panel_context(gym, *, placeholder_form=None, link_form=None):
	"""Shared dashboard context, including the empty-state sections.

	Both coach and student lists exist even when empty: an empty roster
	must render, not break, the panel.
	"""
	return {
		'gym': gym,
		'working_hours': gym.working_hours.all(),
		'linked_coaches': gym.coaches.select_related('user'),
		'placeholders': gym.coach_placeholders.all(),
		'student_count': gym.student_links.count(),
		'placeholder_form': placeholder_form or GymCoachPlaceholderForm(),
		'link_form': link_form or LinkCoachForm(),
	}


@login_required
def create(request):
	"""Flow one of the PRD: the owner's first club, created right after OTP."""
	if request.user.role != User.Role.GYM:
		raise PermissionDenied

	existing = Gym.objects.filter(owner=request.user).first()
	if existing is not None:
		return redirect('gyms:panel')

	if request.method == 'POST':
		form = GymForm(request.POST)
		if form.is_valid():
			# `form.instance` carries the model-clean normalization (phone);
			# `cleaned_data` would pass the raw input straight to the DB.
			instance = form.instance
			gym = create_gym(
				owner=request.user,
				created_by=request.user,
				status=Gym.Status.PENDING,
				name=instance.name,
				phone=instance.phone,
				address=instance.address,
				latitude=instance.latitude,
				longitude=instance.longitude,
			)
			messages.success(request, 'باشگاه شما ساخته شد.')
			return redirect('gyms:panel')
	else:
		form = GymForm()

	return render(request, 'gyms/create.html', {'form': form})


@login_required
def panel(request):
	gym, redirect_response = gym_or_redirect(request)
	if gym is None:
		return redirect_response
	return render(request, 'gyms/panel.html', _panel_context(gym))


@login_required
@require_POST
def coach_placeholder_add(request):
	"""A roster entry for a coach who has not joined the app yet."""
	gym, redirect_response = gym_or_redirect(request)
	if gym is None:
		return redirect_response

	form = GymCoachPlaceholderForm(request.POST)
	if form.is_valid():
		phone = form.cleaned_data.get('phone') or ''
		if phone and gym.coach_placeholders.filter(phone=phone).exists():
			form.add_error('phone', 'مربی دیگری با این شماره در فهرست باشگاه ثبت شده است.')
		else:
			placeholder = form.save(commit=False)
			placeholder.gym = gym
			placeholder.save()
			messages.success(request, 'مربی به فهرست باشگاه اضافه شد.')
			return redirect('gyms:panel')

	messages.error(request, 'اطلاعات مربی را بررسی کنید.')
	return render(request, 'gyms/panel.html', _panel_context(gym, placeholder_form=form))


@login_required
@require_POST
def coach_placeholder_remove(request, pk):
	gym, redirect_response = gym_or_redirect(request)
	if gym is None:
		return redirect_response

	placeholder = gym.coach_placeholders.filter(pk=pk).first()
	if placeholder is None:
		raise Http404
	placeholder.delete()
	messages.success(request, 'مربی از فهرست باشگاه حذف شد.')
	return redirect('gyms:panel')


@login_required
@require_POST
def coach_link(request):
	"""Attach an existing coach account to this club, looked up by phone.

	The lookup stays inside `gyms`: the account comes from `accounts` and the
	reverse `portfolio` relation is read at runtime, so `gyms` never imports
	`coaches` (dependency: coaches → gyms only).
	"""
	gym, redirect_response = gym_or_redirect(request)
	if gym is None:
		return redirect_response

	form = LinkCoachForm(request.POST)
	if form.is_valid():
		phone = form.cleaned_data['phone']
		user = User.objects.filter(phone=phone, role=User.Role.COACH).first()
		if user is None:
			form.add_error(
				'phone',
				'مربی‌ای با این شماره در تاتامی پلاس ثبت نشده است؛ در صورت نیاز به‌صورت متنی اضافه کنید.',
			)
		else:
			portfolio = getattr(user, 'portfolio', None)
			if portfolio is None:
				form.add_error('phone', 'این حساب هنوز پورتفولیوی مربیگری ثبت نکرده است.')
			elif portfolio.gym_id == gym.pk:
				messages.info(request, 'این مربی قبلاً به باشگاه شما متصل شده است.')
				return redirect('gyms:panel')
			elif portfolio.gym_id is not None:
				form.add_error('phone', 'این مربی به باشگاه دیگری متصل است.')
			else:
				portfolio.gym = gym
				portfolio.save(update_fields=['gym', 'updated_at'])
				messages.success(request, 'مربی به باشگاه شما متصل شد.')
				return redirect('gyms:panel')

	messages.error(request, 'شمارهٔ مربی را بررسی کنید.')
	return render(request, 'gyms/panel.html', _panel_context(gym, link_form=form))


@login_required
@require_POST
def coach_unlink(request, pk):
	gym, redirect_response = gym_or_redirect(request)
	if gym is None:
		return redirect_response

	portfolio = gym.coaches.filter(pk=pk).first()
	if portfolio is None:
		raise Http404
	portfolio.gym = None
	portfolio.save(update_fields=['gym', 'updated_at'])
	messages.success(request, 'اتصال مربی به باشگاه برداشته شد.')
	return redirect('gyms:panel')
