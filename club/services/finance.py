from django.utils import timezone

from club.models import EventFeeCharge, Transaction, UserProfile


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def create_pending_event_fee_charge(user, event, amount, *, note=""):
    charge, _ = EventFeeCharge.objects.select_for_update().get_or_create(
        user=user,
        event=event,
        defaults={
            "amount": amount,
            "status": EventFeeCharge.STATUS_PENDING,
            "note": note,
        },
    )
    charge.amount = amount
    charge.status = EventFeeCharge.STATUS_PENDING
    charge.note = note
    charge.payment_transaction = None
    charge.settled_at = None
    charge.settled_by = None
    charge.save(
        update_fields=[
            "amount",
            "status",
            "note",
            "payment_transaction",
            "settled_at",
            "settled_by",
            "updated_at",
        ]
    )
    return charge


def settle_event_fee_charge(charge, *, acting_user=None, transaction_note=""):
    if charge.status == EventFeeCharge.STATUS_SETTLED:
        return charge.payment_transaction

    profile = ensure_profile(charge.user)
    if profile.balance < charge.amount:
        return None

    profile.balance -= charge.amount
    profile.save(update_fields=["balance"])

    event_fee_tx = Transaction.objects.create(
        user=charge.user,
        transaction_type="event_fee",
        amount=charge.amount,
        description=f"Event: {charge.event.title}",
        note=transaction_note,
        status="approved",
        event=charge.event,
        approved_by=acting_user,
        approved_at=timezone.now(),
    )
    charge.status = EventFeeCharge.STATUS_SETTLED
    charge.payment_transaction = event_fee_tx
    charge.settled_at = event_fee_tx.approved_at
    charge.settled_by = acting_user
    if transaction_note:
        charge.note = transaction_note
    charge.save(
        update_fields=[
            "status",
            "payment_transaction",
            "settled_at",
            "settled_by",
            "note",
            "updated_at",
        ]
    )
    return event_fee_tx


def create_settled_event_fee_charge(user, event, amount, *, acting_user=None, transaction_note=""):
    charge, _ = EventFeeCharge.objects.select_for_update().get_or_create(
        user=user,
        event=event,
        defaults={
            "amount": amount,
            "status": EventFeeCharge.STATUS_PENDING,
        },
    )
    charge.amount = amount
    charge.save(update_fields=["amount", "updated_at"])
    return settle_event_fee_charge(
        charge,
        acting_user=acting_user,
        transaction_note=transaction_note,
    )


def cancel_event_fee_charge(user, event, *, note=""):
    charge = (
        EventFeeCharge.objects.select_for_update()
        .filter(user=user, event=event)
        .first()
    )
    if not charge:
        return None

    charge.status = EventFeeCharge.STATUS_CANCELLED
    if note:
        charge.note = note
    charge.save(update_fields=["status", "note", "updated_at"])
    return charge


def settle_pending_event_fee_charges(user, *, acting_user=None):
    settled_transactions = []
    pending_charges = (
        EventFeeCharge.objects.filter(
            user=user,
            status=EventFeeCharge.STATUS_PENDING,
        )
        .select_related("event")
        .order_by("created_at", "id")
    )

    for charge in pending_charges:
        tx = settle_event_fee_charge(
            charge,
            acting_user=acting_user,
            transaction_note="自动补缴此前欠费。",
        )
        if tx is None:
            break
        settled_transactions.append(tx)

    return settled_transactions
