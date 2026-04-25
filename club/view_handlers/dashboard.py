import decimal
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import render

from club.models import EventFeeCharge, SiteSettings, Transaction, UserProfile
from club.models.events import Participation

from .shared import ensure_profile, upcoming_events_queryset

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    logger.info(
        f"Dashboard accessed by user: {request.user.username} "
        f"(staff={request.user.is_staff})"
    )
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.user.is_staff:
        logger.info(f"Rendering admin dashboard for {request.user.username}")
        member_profiles = UserProfile.objects.select_related("user").filter(
            user__is_staff=False
        )
        all_users = member_profiles[:20]
        recent_transactions = Transaction.objects.select_related("user").all()[:10]
        upcoming_events = upcoming_events_queryset()[:10]
        total_balance = (
            member_profiles.aggregate(total=Sum("balance")).get("total")
            or decimal.Decimal("0")
        )
        registered_member_count = User.objects.filter(is_staff=False).count()
        try:
            site_settings = SiteSettings.objects.get(name="default")
        except SiteSettings.DoesNotExist:
            site_settings = None
        context = {
            "balance": profile.balance,
            "all_users": all_users,
            "recent_transactions": recent_transactions,
            "upcoming_events": upcoming_events,
            "total_balance": total_balance,
            "registered_member_count": registered_member_count,
            "site_settings": site_settings,
        }
        return render(request, "club/admin_dashboard.html", context)

    upcoming_events = upcoming_events_queryset().exclude(
        participations__user=request.user,
        participations__status__in=Participation.ACTIVE_STATUSES,
    )[:5]
    my_events = upcoming_events_queryset().filter(
        participations__user=request.user,
        participations__status__in=Participation.ACTIVE_STATUSES,
    )[:5]
    default_price = SiteSettings.get_default_price()
    pending_fee_total = (
        EventFeeCharge.objects.filter(
            user=request.user,
            status=EventFeeCharge.STATUS_PENDING,
        ).aggregate(total=Sum("amount")).get("total")
        or decimal.Decimal("0")
    )
    context = {
        "balance": profile.balance,
        "upcoming_events": upcoming_events,
        "my_events": my_events,
        "event_price": default_price,
        "pending_fee_total": pending_fee_total,
    }
    return render(request, "club/dashboard.html", context)


@login_required
def history(request):
    transactions = Transaction.objects.filter(user=request.user)
    return render(request, "club/history.html", {"transactions": transactions})
