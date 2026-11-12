from django.dispatch import receiver

from accounts.signals import profile_completed
from club.signals import episode_completed
from orders.models import Payment
from orders.signals import payment_succeeded

from .models import GemReason
from .services import award


@receiver(profile_completed)
def award_profile_completion(sender, user, **kwargs):
	# No reference: the unique (user, reason, '', '') row makes this once-only.
	award(user, GemReason.PROFILE_COMPLETE)


@receiver(episode_completed)
def award_episode_completion(sender, user, episode, **kwargs):
	award(user, GemReason.EPISODE_COMPLETE, ref=episode)


@receiver(payment_succeeded, sender=Payment)
def award_purchase(sender, payment, **kwargs):
	"""Shop orders earn gems; course purchases deliberately do not.

	The order id lives in `payment.metadata`, so this receiver needs no extra
	field on Payment and no import of the club app.
	"""
	order_id = (payment.metadata or {}).get('order_id')
	if not order_id:
		return
	award(
		payment.user,
		GemReason.PURCHASE,
		ref_type='order',
		ref_id=str(order_id),
		base_amount=payment.amount,
	)
