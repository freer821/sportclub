from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from club.models import UserProfile
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
        logger.info(f"Created profile for new user: {instance.username}")
    else:
        if not hasattr(instance, 'profile'):
            UserProfile.objects.create(user=instance)
            logger.info(f"Created missing profile for user: {instance.username}")