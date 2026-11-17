from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from .access import coach_profile_or_redirect
from .forms import CoachApplicationForm, CoachInviteForm, CoachProfileForm, InviteCodeEntryForm
from .invites import InviteError, generate_code, redeem
from .models import CoachApplication, CoachInvite, CoachProfile


@login_required
def apply(request):
	if request.user.role != User.Role.COACH:
		raise PermissionDenied

	application = getattr(request.user, 'coach_application', None)
	# Pending and approved requests are read-only here; only a rejection opens
	# the form again, and it reuses the same row so the certificate survives.
	if application is not None and application.status != CoachApplication.Status.REJECTED:
		return redirect('coaches:application_status')

	resubmitting = application is not None
	if request.method == 'POST':
		form = CoachApplicationForm(request.POST, request.FILES, instance=application)
		if form.is_valid():
			application = form.save(commit=False)
			application.user = request.user
			application.status = CoachApplication.Status.PENDING_REVIEW
			application.rejection_reason = ''
			application.reviewed_at = None
			application.full_clean()
			application.save()
			if resubmitting:
				# `auto_now_add` only fires on insert, so record the new attempt.
				CoachApplication.objects.filter(pk=application.pk).update(submitted_at=timezone.now())
				messages.success(request, 'درخواست شما با تغییرات تازه دوباره ارسال شد.')
			else:
				messages.success(request, 'درخواست شما ثبت شد و در انتظار بررسی است.')
			return redirect('coaches:application_status')
	else:
		form = CoachApplicationForm(instance=application)

	return render(request, 'coaches/apply.html', {
		'form': form,
		'resubmitting': resubmitting,
		'application': application,
	})


@login_required
def application_status(request):
	application = get_object_or_404(CoachApplication, user=request.user)
	return render(request, 'coaches/application_status.html', {
		'application': application,
		'profile': getattr(application, 'profile', None),
	})


def directory(request):
	profiles = CoachProfile.objects.filter(
		application__status=CoachApplication.Status.APPROVED,
		is_published=True,
	).select_related('application', 'application__user')
	return render(request, 'coaches/directory.html', {'profiles': profiles})


def profile_detail(request, profile_id):
	profile = get_object_or_404(
		CoachProfile.objects.select_related('application', 'application__user'),
		pk=profile_id,
		application__status=CoachApplication.Status.APPROVED,
		is_published=True,
	)
	return render(request, 'coaches/profile_detail.html', {'profile': profile})


@staff_member_required
def certificate_download(request, application_id):
	application = get_object_or_404(CoachApplication, pk=application_id)
	if not application.certificate_document:
		raise Http404

	return FileResponse(
		application.certificate_document.open('rb'),
		as_attachment=True,
		filename=Path(application.certificate_document.name).name,
	)


@login_required
def portfolio(request):
	"""Edit the coach's own public profile.

	Publication is not on this form: a coach can prepare the page, and the team
	flips `is_published` in Django Admin when it is ready.
	"""
	profile, response = coach_profile_or_redirect(request)
	if response:
		return response

	form = CoachProfileForm(request.POST or None, request.FILES or None, instance=profile)
	if request.method == 'POST' and form.is_valid():
		form.save()
		messages.success(request, 'پروفایل شما ذخیره شد. انتشار آن را تیم تاتامی پلاس بررسی می‌کند.')
		return redirect('coaches:portfolio')

	return render(request, 'coaches/portfolio.html', {
		'profile': profile,
		'form': form,
	})


@login_required
def coach_students(request):
	"""Coach panel: hand out an invite code and see who joined with it."""
	profile, response = coach_profile_or_redirect(request)
	if response:
		return response

	form = CoachInviteForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		invite = form.save(commit=False)
		invite.coach = profile
		invite.code = generate_code()
		invite.save()
		messages.success(request, f'کد دعوت {invite.code} ساخته شد. آن را با هنرجوها به اشتراک بگذارید.')
		return redirect('coach_students:list')

	return render(request, 'coaches/coach_students.html', {
		'profile': profile,
		'invites': profile.invites.order_by('-created_at'),
		'students': profile.students.select_related('student').order_by('-created_at'),
		'form': form,
	})


@login_required
@require_POST
def toggle_invite(request, pk):
	"""Enable or disable a code. The code value never changes."""
	profile, response = coach_profile_or_redirect(request)
	if response:
		return response

	invite = get_object_or_404(profile.invites, pk=pk)
	invite.is_active = not invite.is_active
	invite.save(update_fields=['is_active'])
	if invite.is_active:
		messages.success(request, f'کد {invite.code} فعال شد.')
	else:
		messages.info(request, f'کد {invite.code} غیرفعال شد؛ هنرجویان تازه نمی‌توانند از آن استفاده کنند.')
	return redirect('coach_students:list')


@login_required
def enter_code(request):
	"""Manual entry for a code a student was handed verbally.

	Resolves to the coach first so a typo gets a field error on this page
	instead of a bare 404 on the join page.
	"""
	if request.method == 'POST':
		form = InviteCodeEntryForm(request.POST)
		if form.is_valid():
			code = form.cleaned_data['code']
			if not CoachInvite.objects.filter(code__iexact=code).exists():
				form.add_error('code', 'این کد دعوت پیدا نشد. کد را دوباره بررسی کنید.')
			else:
				return redirect('coaches:join_coach', code=code)
	else:
		form = InviteCodeEntryForm()

	return render(request, 'coaches/join_enter.html', {'form': form})


@login_required
def join_coach(request, code):
	"""Student side: open the code, confirm, and get attached to the coach."""
	invite = (
		CoachInvite.objects.select_related('coach', 'coach__application')
		.filter(code__iexact=code.strip())
		.first()
	)
	if invite is None:
		raise Http404

	if request.method == 'POST':
		try:
			link, created = redeem(invite.code, request.user)
		except InviteError as exc:
			messages.error(request, str(exc))
			return redirect('coaches:join_coach', code=invite.code)
		if created:
			messages.success(request, f'به هنرجویان {invite.coach.display_name} اضافه شدید.')
		else:
			messages.info(request, f'شما از قبل در فهرست هنرجویان {invite.coach.display_name} هستید.')
		return redirect('club:coach_detail', profile_id=invite.coach_id)

	already = request.user.coach_links.filter(coach=invite.coach).exists()
	return render(request, 'coaches/join.html', {'invite': invite, 'already': already})
