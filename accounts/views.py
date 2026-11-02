from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import RegistrationForm
from .models import User


def register(request):
	if request.user.is_authenticated:
		return redirect('account')

	initial_role = request.GET.get('role', User.Role.STUDENT)
	if initial_role not in User.Role.values:
		initial_role = User.Role.STUDENT

	if request.method == 'POST':
		form = RegistrationForm(request.POST)
		if form.is_valid():
			user = form.save()
			login(request, user)
			return redirect('account')
	else:
		form = RegistrationForm(initial={'role': initial_role})

	return render(request, 'accounts/register.html', {'form': form})
