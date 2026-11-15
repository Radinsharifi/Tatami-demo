from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.http import url_has_allowed_host_and_scheme

from .auth_services import OTPError, OTPInvalid, OTPRateLimitExceeded, send_otp, verify_otp
from .forms import OTPVerifyForm, PhoneLoginForm, ProfileCompletionForm
from .models import User


def register(request):
	query = {'role': request.GET.get('role', User.Role.STUDENT)}
	next_url = _safe_next(request, request.GET.get('next'))
	if next_url:
		query['next'] = next_url
	return redirect(f"{reverse('phone_auth:login')}?{urlencode(query)}")


def legacy_login_redirect(request):
	query = {}
	next_url = _safe_next(request, request.GET.get('next'))
	if next_url:
		query['next'] = next_url
	return redirect(f"{reverse('phone_auth:login')}?{urlencode(query)}" if query else 'phone_auth:login')


def _safe_next(request, value):
	if value and url_has_allowed_host_and_scheme(value, {request.get_host()}, require_https=request.is_secure()):
		return value
	return ''


def phone_login(request):
	if request.user.is_authenticated:
		return redirect('account')

	if request.method == 'POST':
		form = PhoneLoginForm(request.POST)
		if form.is_valid():
			phone = form.cleaned_data['phone']
			role = form.cleaned_data['role']
			try:
				send_otp(phone, request.META.get('REMOTE_ADDR'))
			except OTPRateLimitExceeded:
				form.add_error('phone', 'برای ارسال دوبارهٔ کد کمی صبر کنید.')
			except ImproperlyConfigured:
				form.add_error(None, 'ارسال پیامک در این محیط پیکربندی نشده است.')
			else:
				request.session['otp_phone'] = phone
				request.session['otp_role'] = role
				request.session['otp_next'] = _safe_next(request, form.cleaned_data.get('next_url'))
				return redirect('phone_auth:verify_otp')
	else:
		form = PhoneLoginForm(initial={
			'role': User.Role.COACH if request.GET.get('role') == User.Role.COACH else User.Role.STUDENT,
			'next_url': _safe_next(request, request.GET.get('next')),
		})

	return render(request, 'accounts/login.html', {'form': form})


def send_otp_view(request):
	if request.method != 'POST':
		return HttpResponseNotAllowed(['POST'])
	phone = request.session.get('otp_phone')
	if not phone:
		return redirect('phone_auth:login')
	try:
		send_otp(phone, request.META.get('REMOTE_ADDR'))
	except OTPRateLimitExceeded:
		return render(request, 'accounts/otp_verify.html', {
			'form': OTPVerifyForm(),
			'phone_hint': f'****{phone[-4:]}',
			'error': 'برای ارسال دوبارهٔ کد کمی صبر کنید.',
		})
	except ImproperlyConfigured:
		return render(request, 'accounts/otp_verify.html', {
			'form': OTPVerifyForm(),
			'phone_hint': f'****{phone[-4:]}',
			'error': 'ارسال پیامک در این محیط پیکربندی نشده است.',
		})
	return redirect('phone_auth:verify_otp')


def verify_otp_view(request):
	phone = request.session.get('otp_phone')
	role = request.session.get('otp_role')
	if not phone or role not in User.Role.values:
		return redirect('phone_auth:login')

	if request.method == 'POST':
		form = OTPVerifyForm(request.POST)
		if form.is_valid():
			try:
				user, _ = verify_otp(phone, form.cleaned_data['code'], role)
			except OTPInvalid:
				form.add_error('code', 'کد نامعتبر یا منقضی شده است. دوباره درخواست کد کنید.')
			else:
				login(request, user, backend='django.contrib.auth.backends.ModelBackend')
				next_url = request.session.get('otp_next', '')
				request.session.pop('otp_phone', None)
				request.session.pop('otp_role', None)
				if not user.is_profile_complete:
					return redirect('phone_auth:complete_profile')
				request.session.pop('otp_next', None)
				return redirect(next_url or 'account')
	else:
		form = OTPVerifyForm()

	return render(request, 'accounts/otp_verify.html', {'form': form, 'phone_hint': f'****{phone[-4:]}'})


@login_required
def complete_profile(request):
	if request.user.is_profile_complete:
		return redirect('account')
	if request.method == 'POST':
		form = ProfileCompletionForm(request.POST)
		if form.is_valid():
			form.save(request.user)
			return redirect(request.session.pop('otp_next', '') or 'account')
	else:
		form = ProfileCompletionForm(initial={'role': request.user.role})
	return render(request, 'accounts/complete_profile.html', {'form': form})


def account(request):
	"""The signed-in landing page, including the coach request's current state.

	`accounts` must not import `coaches`, so the reverse OneToOne is read with
	`getattr`; a missing application is simply "has not applied yet".
	"""
	application = None
	profile = None
	if request.user.is_authenticated and request.user.role == User.Role.COACH:
		application = getattr(request.user, 'coach_application', None)
		if application is not None:
			profile = getattr(application, 'profile', None)

	return render(request, 'pages/account.html', {
		'coach_application': application,
		'coach_profile': profile,
	})
