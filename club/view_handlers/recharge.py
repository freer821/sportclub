import decimal
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from club.forms import AdminRechargeForm, RechargeForm
from club.models import Event, EventFeeCharge, Transaction
from club.services import ensure_profile, settle_pending_event_fee_charges

logger = logging.getLogger(__name__)

SOURCE_LABELS = dict(Transaction.RECHARGE_SOURCE_CHOICES)


def recharge_description(source, status):
    source_label = SOURCE_LABELS.get(source, source or "其他")
    if status == "pending":
        return f"充值申请（{source_label}）"
    return f"充值已到账（{source_label}）"


def update_transaction_created_at(recharge_tx, recharge_time):
    if recharge_time is None:
        return
    Transaction.objects.filter(pk=recharge_tx.pk).update(created_at=recharge_time)
    recharge_tx.created_at = recharge_time


def apply_recharge_credit(user, amount, *, acting_user=None):
    profile = ensure_profile(user)
    profile.balance += amount
    profile.save(update_fields=["balance"])
    settle_pending_event_fee_charges(user, acting_user=acting_user)
    profile.refresh_from_db()
    return profile


@login_required
def recharge(request):
    if request.user.is_staff:
        messages.error(request, "Administrators cannot use this page.")
        return redirect("dashboard")

    if request.method == "POST":
        form = RechargeForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            source = form.cleaned_data["source"]
            note = form.cleaned_data["note"]
            Transaction.objects.create(
                user=request.user,
                transaction_type="recharge",
                amount=amount,
                source=source,
                note=note,
                status="pending",
                description=recharge_description(source, "pending"),
            )
            messages.success(request, "充值申请已提交，等待管理员审核后才会入账。")
            return redirect("dashboard")
    else:
        form = RechargeForm()
    pending_recharges = Transaction.objects.filter(
        user=request.user,
        transaction_type="recharge",
        status="pending",
    ).order_by("-created_at")[:5]
    return render(
        request,
        "club/recharge.html",
        {"form": form, "pending_recharges": pending_recharges},
    )


@login_required
def admin_recharge(request):
    if not request.user.is_staff:
        logger.warning(
            f"Non-admin user {request.user.username} attempted to access admin recharge"
        )
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    if request.method == "POST":
        form = AdminRechargeForm(request.POST)
        if form.is_valid():
            user_id = form.cleaned_data["user_id"]
            amount = form.cleaned_data["amount"]
            source = form.cleaned_data.get("source", "other")
            note = form.cleaned_data.get("note", "")
            recharge_time = form.cleaned_data.get("recharge_time")
            target_user = User.objects.filter(id=user_id, is_staff=False).first()
            if target_user is None:
                messages.error(request, "Target member does not exist.")
                return redirect("admin_recharge")
            with transaction.atomic():
                profile = apply_recharge_credit(
                    target_user,
                    amount,
                    acting_user=request.user,
                )
                recharge_tx = Transaction.objects.create(
                    user=target_user,
                    transaction_type="recharge",
                    amount=amount,
                    source=source,
                    note=note,
                    status="approved",
                    approved_by=request.user,
                    approved_at=recharge_time if recharge_time else timezone.now(),
                    description=recharge_description(source, "approved"),
                )
                update_transaction_created_at(recharge_tx, recharge_time)
            logger.info(
                f"Admin {request.user.username} recharged {amount}EUR to user "
                f"{target_user.username}"
            )
            messages.success(
                request,
                f"Successfully recharged {amount}EUR to {target_user.username}",
            )
            return redirect("admin_recharge")
    else:
        form = AdminRechargeForm()

    users = User.objects.filter(is_staff=False).select_related("profile")
    pending_recharge_transactions = (
        Transaction.objects.filter(
            transaction_type="recharge",
            status="pending",
        )
        .select_related("user")
        .order_by("-created_at")
    )
    completed_recharge_transactions = (
        Transaction.objects.filter(
            transaction_type="recharge",
            status="approved",
        )
        .select_related("user", "approved_by")
        .order_by("-created_at")[:20]
    )

    return render(
        request,
        "club/admin_recharge.html",
        {
            "form": form,
            "users": users,
            "pending_recharge_transactions": pending_recharge_transactions,
            "completed_recharge_transactions": completed_recharge_transactions,
        },
    )


@login_required
def admin_fee_management(request):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can access this page.")
        return redirect("dashboard")

    pending_fee_transactions = (
        EventFeeCharge.objects.filter(
            status=EventFeeCharge.STATUS_PENDING,
        )
        .select_related("user", "event")
        .order_by("-created_at")
    )
    completed_fee_transactions = Transaction.objects.filter(
        transaction_type="event_fee",
        status="approved",
    ).select_related("user", "event", "approved_by").order_by("-created_at")[:50]
    event_fee_stats = (
        Event.objects.annotate(
            approved_revenue=Coalesce(
                Sum(
                    "fee_charges__amount",
                    filter=Q(
                        fee_charges__status=EventFeeCharge.STATUS_SETTLED,
                    ),
                ),
                Value(decimal.Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            pending_revenue=Coalesce(
                Sum(
                    "fee_charges__amount",
                    filter=Q(
                        fee_charges__status=EventFeeCharge.STATUS_PENDING,
                    ),
                ),
                Value(decimal.Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            approved_fee_count=Count(
                "fee_charges",
                filter=Q(
                    fee_charges__status=EventFeeCharge.STATUS_SETTLED,
                ),
            ),
            pending_fee_count=Count(
                "fee_charges",
                filter=Q(
                    fee_charges__status=EventFeeCharge.STATUS_PENDING,
                ),
            ),
        )
        .filter(
            Q(approved_fee_count__gt=0) | Q(pending_fee_count__gt=0)
        )
        .order_by("-date")
    )
    approved_fee_total = (
        EventFeeCharge.objects.filter(
            status=EventFeeCharge.STATUS_SETTLED,
        ).aggregate(total=Sum("amount")).get("total")
        or decimal.Decimal("0.00")
    )
    pending_fee_total = (
        EventFeeCharge.objects.filter(
            status=EventFeeCharge.STATUS_PENDING,
        ).aggregate(total=Sum("amount")).get("total")
        or decimal.Decimal("0.00")
    )

    return render(
        request,
        "club/admin_fee_management.html",
        {
            "pending_fee_transactions": pending_fee_transactions,
            "completed_fee_transactions": completed_fee_transactions,
            "event_fee_stats": event_fee_stats,
            "approved_fee_total": approved_fee_total,
            "pending_fee_total": pending_fee_total,
        },
    )


@login_required
@require_POST
def update_admin_recharge(request, transaction_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can update recharges.")
        return redirect("dashboard")

    recharge_tx = get_object_or_404(
        Transaction,
        id=transaction_id,
        transaction_type="recharge",
    )
    amount_raw = request.POST.get("amount", "").strip()
    source = request.POST.get("source", "").strip() or "other"
    note = request.POST.get("note", "").strip()
    try:
        new_amount = decimal.Decimal(amount_raw)
    except decimal.InvalidOperation:
        messages.error(request, "Amount is invalid.")
        return redirect("admin_recharge")
    if new_amount <= 0:
        messages.error(request, "Amount must be greater than 0.")
        return redirect("admin_recharge")
    if source not in SOURCE_LABELS:
        messages.error(request, "Source is invalid.")
        return redirect("admin_recharge")

    with transaction.atomic():
        old_amount = recharge_tx.amount
        if recharge_tx.status == "approved":
            delta = new_amount - old_amount
            profile = ensure_profile(recharge_tx.user)
            if profile.balance + delta < 0:
                messages.error(
                    request,
                    (
                        f"Cannot update: {recharge_tx.user.username} balance is too low "
                        "for this change."
                    ),
                )
                return redirect("admin_recharge")
            profile.balance += delta
            profile.save(update_fields=["balance"])
        recharge_tx.amount = new_amount
        recharge_tx.source = source
        recharge_tx.note = note
        recharge_tx.description = recharge_description(source, recharge_tx.status)
        recharge_tx.save(update_fields=["amount", "source", "note", "description"])

    messages.success(
        request,
        f"Updated recharge #{recharge_tx.id}: {old_amount}EUR -> {new_amount}EUR.",
    )
    return redirect("admin_recharge")


@login_required
@require_POST
def approve_admin_recharge(request, transaction_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can approve recharges.")
        return redirect("dashboard")

    recharge_tx = get_object_or_404(
        Transaction,
        id=transaction_id,
        transaction_type="recharge",
    )
    if recharge_tx.status != "pending":
        messages.error(request, "This recharge has already been approved.")
        return redirect("admin_recharge")

    with transaction.atomic():
        profile = apply_recharge_credit(
            recharge_tx.user,
            recharge_tx.amount,
            acting_user=request.user,
        )
        recharge_tx.status = "approved"
        recharge_tx.approved_by = request.user
        recharge_tx.approved_at = timezone.now()
        recharge_tx.description = recharge_description(
            recharge_tx.source,
            recharge_tx.status,
        )
        recharge_tx.save(
            update_fields=["status", "approved_by", "approved_at", "description"]
        )

    messages.success(
        request,
        f"Approved recharge #{recharge_tx.id} for {recharge_tx.user.username}.",
    )
    return redirect("admin_recharge")


@login_required
@require_POST
def quick_recharge(request, user_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can perform quick recharges.")
        return redirect("dashboard")

    target_user = User.objects.filter(id=user_id, is_staff=False).first()
    if target_user is None:
        messages.error(request, "Target member does not exist.")
        return redirect("admin_recharge")

    amount_raw = request.POST.get("amount", "").strip()
    try:
        amount = decimal.Decimal(amount_raw)
    except decimal.InvalidOperation:
        messages.error(request, "Invalid amount.")
        return redirect("admin_recharge")

    if amount <= 0:
        messages.error(request, "Amount must be greater than 0.")
        return redirect("admin_recharge")

    with transaction.atomic():
        profile = apply_recharge_credit(
            target_user,
            amount,
            acting_user=request.user,
        )
        Transaction.objects.create(
            user=target_user,
            transaction_type="recharge",
            amount=amount,
            source=request.POST.get("source", "other"),
            note=request.POST.get("note", "").strip(),
            status="approved",
            approved_by=request.user,
            approved_at=timezone.now(),
            description=recharge_description(
                request.POST.get("source", "other"),
                "approved",
            ),
        )

    logger.info(
        f"Admin {request.user.username} quick recharged {amount}EUR to user "
        f"{target_user.username}"
    )
    messages.success(
        request,
        f"Successfully recharged {amount}EUR to {target_user.username}",
    )
    return redirect("admin_recharge")


@login_required
@require_POST
def delete_admin_recharge(request, transaction_id):
    if not request.user.is_staff:
        messages.error(request, "Only administrators can delete recharges.")
        return redirect("dashboard")

    recharge_tx = get_object_or_404(
        Transaction,
        id=transaction_id,
        transaction_type="recharge",
    )

    with transaction.atomic():
        if recharge_tx.status == "approved":
            profile = ensure_profile(recharge_tx.user)
            if profile.balance < recharge_tx.amount:
                messages.error(
                    request,
                    (
                        f"Cannot delete: {recharge_tx.user.username} balance is lower "
                        f"than {recharge_tx.amount}EUR."
                    ),
                )
                return redirect("admin_recharge")
            profile.balance -= recharge_tx.amount
            profile.save(update_fields=["balance"])
        recharge_tx.delete()

    messages.success(request, "Recharge record deleted successfully.")
    return redirect("admin_recharge")
