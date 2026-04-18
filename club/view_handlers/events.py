import decimal
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from club.forms import EventForm
from club.models import Event, Participation, SiteSettings, Transaction

from .shared import ensure_profile, upcoming_events_queryset

logger = logging.getLogger(__name__)


@login_required
def event_list(request):
    events = Event.objects.filter(date__gte=timezone.now())
    user_participations = Participation.objects.filter(
        user=request.user,
        status="registered",
    ).values_list("event_id", flat=True)
    default_price = SiteSettings.get_default_price()
    return render(
        request,
        "club/event_list.html",
        {
            "events": events,
            "user_participations": list(user_participations),
            "event_price": default_price,
        },
    )


@login_required
def join_event(request, event_id):
    logger.info(f"User {request.user.username} attempting to join event {event_id}")
    event = get_object_or_404(Event, id=event_id)
    event_price = decimal.Decimal(event.event_price)

    if event.date < timezone.now():
        messages.error(request, "This event has already passed.")
        return redirect("event_list")

    if event.is_full:
        messages.error(request, "This event is full.")
        return redirect("event_list")

    with transaction.atomic():
        profile = ensure_profile(request.user)
        participation = Participation.objects.filter(
            user=request.user,
            event=event,
        ).first()

        if participation and participation.status == "registered":
            messages.warning(request, "You are already registered for this event.")
            return redirect("event_list")

        if profile.balance < event_price:
            messages.error(
                request,
                f"Insufficient balance. You need at least {event_price}EUR to join.",
            )
            return redirect("recharge")

        profile.balance -= event_price
        profile.save(update_fields=["balance"])

        if participation:
            participation.status = "registered"
            participation.save(update_fields=["status"])
        else:
            Participation.objects.create(
                user=request.user,
                event=event,
                status="registered",
            )

        Transaction.objects.create(
            user=request.user,
            transaction_type="event_fee",
            amount=event_price,
            description=f"Event: {event.title}",
            event=event,
        )

    logger.info(
        f"User {request.user.username} joined event {event.title}, "
        f"deducted {event_price}EUR"
    )
    messages.success(
        request,
        f"Successfully joined {event.title}! {event_price}EUR has been deducted.",
    )
    return redirect("event_list")


@login_required
def leave_event(request, event_id):
    logger.info(f"User {request.user.username} attempting to leave event {event_id}")
    event = get_object_or_404(Event, id=event_id)
    event_price = decimal.Decimal(event.event_price)

    participation = Participation.objects.filter(
        user=request.user,
        event=event,
        status="registered",
    ).first()

    if not participation:
        messages.warning(request, "You are not registered for this event.")
        return redirect("event_list")

    if event.date < timezone.now():
        messages.error(request, "Cannot leave past events.")
        return redirect("event_list")

    with transaction.atomic():
        participation.status = "cancelled"
        participation.save(update_fields=["status"])

        profile = ensure_profile(request.user)
        profile.balance += event_price
        profile.save(update_fields=["balance"])

        Transaction.objects.create(
            user=request.user,
            transaction_type="refund",
            amount=event_price,
            description=f"Refund for cancelled: {event.title}",
            event=event,
        )

    messages.success(
        request,
        f"Successfully left {event.title}. {event_price}EUR has been refunded.",
    )
    return redirect("event_list")


@login_required
def create_event(request):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can create events.")
        return redirect("dashboard")

    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            start_dt, end_dt = form.build_datetimes()
            title = form.cleaned_data["title"]
            description = form.cleaned_data["description"]
            location = form.cleaned_data["location"]
            repeat_mode = form.cleaned_data.get("repeat_mode") or "none"
            repeat_count = form.cleaned_data.get("repeat_count") or 1
            repeat_delta = timedelta(weeks=2) if repeat_mode == "biweekly" else timedelta(weeks=1)

            created_events = []
            occurrences = repeat_count if repeat_mode != "none" else 1
            for index in range(occurrences):
                offset = repeat_delta * index if repeat_mode != "none" else timedelta(0)
                event = Event(
                    title=title,
                    description=description,
                    location=location,
                    date=start_dt + offset,
                    end_time=end_dt + offset,
                    price=None,
                    created_by=request.user,
                )
                event.save()
                created_events.append(event)
            if len(created_events) == 1:
                messages.success(request, f'Event "{created_events[0].title}" created successfully!')
            else:
                messages.success(
                    request,
                    f'Event series "{created_events[0].title}" created successfully! 共创建 {len(created_events)} 场活动。',
                )
            return redirect("event_list")
    else:
        form = EventForm()
    return render(request, "club/create_event.html", {"form": form})


@login_required
def event_participants(request, event_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can view participant lists.")
        return redirect("dashboard")

    event = get_object_or_404(Event, id=event_id)
    participants = Participation.objects.filter(
        event=event,
        status="registered",
    ).select_related("user")
    return render(
        request,
        "club/event_participants.html",
        {
            "event": event,
            "participants": participants,
        },
    )


@login_required
def admin_events(request):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    events = Event.objects.all().order_by("-date")
    total_collected_fees = sum(event.total_fee_amount for event in events)
    return render(
        request,
        "club/admin_events.html",
        {
            "events": events,
            "total_collected_fees": total_collected_fees,
        },
    )


@login_required
def admin_event_delete(request, event_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    event = get_object_or_404(Event, id=event_id)
    event.delete()
    messages.success(request, "活动已删除")
    return redirect("admin_events")


@login_required
def api_events(request):
    events = upcoming_events_queryset()
    data = [
        {
            "id": event.id,
            "title": event.title,
            "start": event.date.isoformat(),
            "end": event.end_time.isoformat() if event.end_time else None,
            "location": event.location,
            "participants": event.participant_count,
            "max": event.max_participants,
        }
        for event in events
    ]
    return JsonResponse(data, safe=False)
