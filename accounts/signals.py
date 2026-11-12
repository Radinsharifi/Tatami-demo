from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import SignupLead, User


@receiver(post_save, sender=User)
def create_coach_signup_lead(sender, instance, created, **kwargs):
	if created and instance.role == User.Role.COACH:
		SignupLead.objects.get_or_create(user=instance)