from django.db.models import Q
from django.utils import timezone

from club.models import Event, UserProfile


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def upcoming_events_queryset():
    now = timezone.now()
    return Event.objects.filter(
        Q(end_time__gte=now) | Q(end_time__isnull=True, date__gte=now)
    ).order_by("date")
