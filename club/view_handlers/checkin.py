import io
from urllib.parse import urlencode

import segno
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from club.forms import QRCheckInForm
from club.models import Event
from club.services import (
    CheckInError,
    available_checkin_events_queryset,
    build_checkin_link,
    default_checkin_event,
    register_user_for_event,
    resolve_user_from_checkin_token,
)


def _localized_text(request, zh, de=None, en=None):
    language_code = (getattr(request, "LANGUAGE_CODE", "") or "").lower()
    if language_code.startswith("de"):
        return de or zh
    if language_code.startswith("en"):
        return en or zh
    return zh


def _selected_event_from_form(form, events):
    raw_event_id = form.data.get("event") if form.is_bound else form.initial.get("event")
    try:
        return events.get(pk=raw_event_id)
    except (Event.DoesNotExist, TypeError, ValueError):
        return events.first()


def _resolve_checkin_user(token):
    try:
        return resolve_user_from_checkin_token(token)
    except (User.DoesNotExist, signing.BadSignature):
        raise Http404("Invalid member check-in link.")


def _render_qr_svg_response(checkin_url):
    qr = segno.make(checkin_url)
    svg_bytes = io.BytesIO()
    qr.save(
        svg_bytes,
        kind="svg",
        scale=6,
        border=2,
        dark="#111827",
        light="#ffffff",
    )
    return HttpResponse(svg_bytes.getvalue(), content_type="image/svg+xml")


@login_required
def member_checkin_qr_svg(request):
    if request.user.is_staff:
        return redirect("dashboard")
    return _render_qr_svg_response(build_checkin_link(request, request.user))


@login_required
def admin_member_checkin_qr_svg(request, user_id):
    if not request.user.is_staff:
        return redirect("dashboard")
    target_user = get_object_or_404(User, id=user_id, is_staff=False)
    return _render_qr_svg_response(build_checkin_link(request, target_user))


def qr_checkin(request):
    token = request.POST.get("token") or request.GET.get("token")
    if not token:
        raise Http404("Missing member check-in token.")

    member = _resolve_checkin_user(token)
    events = available_checkin_events_queryset()
    preferred_event = default_checkin_event(events)

    initial_event_id = request.GET.get("event")
    initial = {}
    if initial_event_id and events.filter(pk=initial_event_id).exists():
        initial["event"] = initial_event_id
    elif preferred_event is not None:
        initial["event"] = preferred_event.pk

    if request.method == "POST":
        form = QRCheckInForm(request.POST, events=events)
        if form.is_valid():
            event = form.cleaned_data["event"]
            try:
                result = register_user_for_event(
                    member,
                    event,
                    mark_attended=True,
                    require_started=True,
                    allow_insufficient_balance=True,
                )
            except CheckInError as exc:
                messages.error(request, str(exc))
            else:
                if result.status == "already_checked_in":
                    messages.info(
                        request,
                        _localized_text(
                            request,
                            f"{member.username} 已完成 {event.title} 的打卡。",
                            f"{member.username} hat den Check-in fuer {event.title} bereits abgeschlossen.",
                            f"{member.username} has already checked in for {event.title}.",
                        ),
                    )
                elif result.status == "checked_in_from_existing":
                    messages.success(
                        request,
                        _localized_text(
                            request,
                            f"{event.title} 打卡成功，已确认到场，不会重复扣费。",
                            f"Check-in fuer {event.title} erfolgreich. Anwesenheit bestaetigt, keine doppelte Abbuchung.",
                            f"Check-in for {event.title} completed. Attendance confirmed with no duplicate charge.",
                        ),
                    )
                elif result.status == "checked_in_pending_balance":
                    messages.warning(
                        request,
                        _localized_text(
                            request,
                            f"{event.title} 打卡成功，已记录 {result.amount}EUR 费用，当前余额不足，待后续补缴。",
                            f"Check-in fuer {event.title} erfolgreich. {result.amount} EUR wurden erfasst, der Betrag ist noch offen.",
                            f"Check-in for {event.title} completed. {result.amount} EUR has been recorded and remains unpaid.",
                        ),
                    )
                else:
                    messages.success(
                        request,
                        _localized_text(
                            request,
                            f"{event.title} 打卡成功，已记录 {result.amount}EUR 费用。",
                            f"Check-in fuer {event.title} erfolgreich. {result.amount} EUR wurden verbucht.",
                            f"Check-in for {event.title} completed. {result.amount} EUR has been recorded.",
                        ),
                    )
                query_string = urlencode({"token": token, "event": event.pk})
                return redirect(f"{reverse('qr_checkin')}?{query_string}")
    else:
        form = QRCheckInForm(events=events, initial=initial)

    selected_event = _selected_event_from_form(form, events) or preferred_event
    return render(
        request,
        "club/qr_checkin.html",
        {
            "form": form,
            "member": member,
            "selected_event": selected_event,
            "has_available_events": events.exists(),
            "token": token,
        },
    )
