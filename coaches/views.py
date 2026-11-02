from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from .forms import CoachApplicationForm
from .models import CoachApplication, CoachProfile


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
