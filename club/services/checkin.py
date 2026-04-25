import decimal
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from club.models import Event, Participation, Transaction, UserProfile

CHECKIN_TOKEN_SALT = "club.member.checkin"


class CheckInError(Exception):
    pass


@dataclass(frozen=True)
class EventRegistrationResult:
    status: str
    amount: decimal.Decimal
    balance_charged: decimal.Decimal


def build_checkin_token(user):
    return signing.dumps({"user_id": user.pk}, salt=CHECKIN_TOKEN_SALT, compress=True)


def build_checkin_link(request, user):
    token = build_checkin_token(user)
    query_string = urlencode({"token": token})
    return request.build_absolute_uri(f"{reverse('qr_checkin')}?{query_string}")


def resolve_user_from_checkin_token(token):
    payload = signing.loads(token, salt=CHECKIN_TOKEN_SALT)
    return User.objects.get(pk=payload["user_id"], is_staff=False, is_active=True)


def available_checkin_events_queryset():
    now = timezone.now()
    return Event.objects.filter(date__lte=now).filter(
        Q(end_time__isnull=True) | Q(end_time__gte=now)
    ).order_by("date")


def register_user_for_event(
    user,
    event,
    *,
    mark_attended=False,
    require_started=False,
    allow_insufficient_balance=False,
):
    now = timezone.now()
    if require_started and event.date > now:
        raise CheckInError("活动尚未开始，暂时不能打卡。")
    if not require_started and event.date < now:
        raise CheckInError("This event has already passed.")
    if event.end_time and event.end_time < now:
        raise CheckInError("该活动已结束，不能再打卡。")

    event_price = decimal.Decimal(event.event_price)

    with transaction.atomic():
        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
        participation = (
            Participation.objects.select_for_update()
            .filter(user=user, event=event)
            .first()
        )

        if participation and participation.status == Participation.STATUS_ATTENDED:
            return EventRegistrationResult(
                status="already_checked_in" if mark_attended else "already_joined",
                amount=decimal.Decimal("0"),
                balance_charged=decimal.Decimal("0"),
            )

        if participation and participation.status == Participation.STATUS_REGISTERED:
            if mark_attended:
                participation.status = Participation.STATUS_ATTENDED
                participation.save(update_fields=["status"])
                return EventRegistrationResult(
                    status="checked_in_from_existing",
                    amount=decimal.Decimal("0"),
                    balance_charged=decimal.Decimal("0"),
                )
            return EventRegistrationResult(
                status="already_joined",
                amount=decimal.Decimal("0"),
                balance_charged=decimal.Decimal("0"),
            )

        if not participation and event.is_full:
            raise CheckInError("This event is full.")

        transaction_status = "approved"
        transaction_note = ""
        charged_amount = event_price

        if profile.balance < event_price and not allow_insufficient_balance:
            raise CheckInError(
                f"余额不足，需要至少 {event_price}EUR 才能完成本次签到。"
                if mark_attended
                else f"Insufficient balance. You need at least {event_price}EUR to join."
            )

        if profile.balance >= event_price:
            profile.balance -= event_price
            profile.save(update_fields=["balance"])
        else:
            charged_amount = decimal.Decimal("0")
            transaction_status = "pending"
            transaction_note = (
                f"余额不足，签到已记录，待补缴 {event_price}EUR。"
                f" 签到时余额 {profile.balance}EUR。"
            )

        participation_status = (
            Participation.STATUS_ATTENDED if mark_attended else Participation.STATUS_REGISTERED
        )
        if participation:
            participation.status = participation_status
            participation.save(update_fields=["status"])
        else:
            Participation.objects.create(
                user=user,
                event=event,
                status=participation_status,
            )

        Transaction.objects.create(
            user=user,
            transaction_type="event_fee",
            amount=event_price,
            description=f"Event: {event.title}",
            note=transaction_note,
            status=transaction_status,
            event=event,
        )

    return EventRegistrationResult(
        status=(
            "checked_in_pending_balance"
            if mark_attended and transaction_status == "pending"
            else "checked_in" if mark_attended else "joined"
        ),
        amount=event_price,
        balance_charged=charged_amount,
    )
