from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import CoachApplication, CoachProfile

# Sent once per newly-created CoachStudent row. `gems` listens to this so the
# coaches app never has to import the ledger; both the student and the coach
# are paid from rules the team edits in Django Admin.
student_attached = Signal()


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
	profile, _ = CoachProfile.objects.get_or_create(
		application=instance,
		defaults={'display_name': name[:100], 'biography': ''},
	)

	# Imported here, not at module level: invites.py imports this module for
	# the signal, so a top-level import would be circular.
	from .invites import ensure_personal_invite

	ensure_personal_invite(profile)
