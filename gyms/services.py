from datetime import time

from django.db import transaction

from .models import Gym, GymWorkingHour

# Editable starting values, not confirmed prices or policy: Saturday through
# Thursday 09:00–22:00, Friday closed. Owners and admins edit them later.
WORKING_HOUR_DEFAULTS = {
	GymWorkingHour.Day.SATURDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.SUNDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.MONDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.TUESDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.WEDNESDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.THURSDAY: (time(9, 0), time(22, 0), False),
	GymWorkingHour.Day.FRIDAY: (None, None, True),
}


def ensure_working_hours(gym):
	"""Create any missing weekly row; idempotent for both creation paths.

	Never blocks creation: a club without hours gets the defaults, and an
	admin who filled some rows inline keeps them while the rest are filled in.
	"""
	for day, (opens, closes, is_closed) in WORKING_HOUR_DEFAULTS.items():
		GymWorkingHour.objects.get_or_create(
			gym=gym,
			day=day,
			defaults={'opens': opens, 'closes': closes, 'is_closed': is_closed},
		)
	return gym.working_hours.all()


@transaction.atomic
def create_gym(*, owner=None, created_by=None, status=Gym.Status.PENDING, **fields):
	"""One shared creation path: same row whether the owner or an admin saves it."""
	gym = Gym.objects.create(owner=owner, created_by=created_by, status=status, **fields)
	ensure_working_hours(gym)
	return gym
