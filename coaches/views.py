from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from .access import coach_profile_or_redirect
from .forms import CoachApplicationForm, CoachInviteForm
from .invites import InviteError, generate_code, redeem
from .models import CoachApplication, CoachInvite, CoachProfile


@login_required
def apply(request):
	if request.user.role != User.Role.COACH:
		raise PermissionDenied
	if CoachApplication.objects.filter(user=request.user).exists():
		return redirect('coaches:application_status')

	if request.method == 'POST':
		form = CoachApplicationForm(request.POST, request.FILES)
		if form.is_valid():
			application = form.save(commit=False)
			application.user = request.user
			application.full_clean()
			application.save()
			return redirect('coaches:application_status')
	else:
		form = CoachApplicationForm()

	return render(request, 'coaches/apply.html', {'form': form})


@login_required
def application_status(request):
	application = get_object_or_404(CoachApplication, user=request.user)
	return render(request, 'coaches/application_status.html', {'application': application})


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
