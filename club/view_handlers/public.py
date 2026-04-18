import logging

from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from club.forms import CustomUserCreationForm
from club.models import SiteSettings

from .shared import upcoming_events_queryset

logger = logging.getLogger(__name__)


def home(request):
    logger.info(f"Home page accessed by {request.user}")
    upcoming_events = upcoming_events_queryset()[:6]
    default_price = SiteSettings.get_default_price()
    context = {
        "upcoming_events": upcoming_events,
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
