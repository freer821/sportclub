import logging
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils import timezone

from club.forms import CustomUserCreationForm
from club.models import SiteSettings

from .shared import upcoming_events_queryset

logger = logging.getLogger(__name__)


def home(request):
    logger.info(f"Home page accessed by {request.user}")
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    start_of_today = timezone.make_aware(datetime.combine(today, time.min), tz)
    start_of_tomorrow = start_of_today + timedelta(days=1)

    today_events = upcoming_events_queryset().filter(
        date__gte=start_of_today,
        date__lt=start_of_tomorrow,
    )
    featured_event = today_events.first() or upcoming_events_queryset().first()
    upcoming_events = [featured_event] if featured_event else []
    default_price = SiteSettings.get_default_price()
    context = {
        "upcoming_events": upcoming_events,
        "featured_event": featured_event,
        "featured_event_is_today": bool(
            featured_event and timezone.localtime(featured_event.date).date() == today
        ),
        "event_price": default_price,
    }
    return render(request, "club/home.html", context)


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                "Registration successful! Welcome to the basketball club.",
            )
            return redirect("dashboard")
    else:
        form = CustomUserCreationForm()
    return render(request, "club/register.html", {"form": form})
