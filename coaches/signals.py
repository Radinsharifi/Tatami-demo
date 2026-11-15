from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CoachApplication, CoachProfile


@receiver(post_save, sender=CoachApplication)
def create_profile_when_approved(sender, instance, **kwargs):
	"""Every approved coach gets an (unpublished) profile to fill in.

	Publication stays a team decision; this only removes the dead end where an
	approved coach had no profile row, so every panel redirected them to the
	application status page.
	"""
	if instance.status != CoachApplication.Status.APPROVED:
		return

	name = (
		instance.user.get_full_name()
		or instance.user.first_name
		or instance.user.phone
		or 'مربی تاتامی پلاس'
	)
	CoachProfile.objects.get_or_create(
		application=instance,
		defaults={'display_name': name[:100], 'biography': ''},
	)
