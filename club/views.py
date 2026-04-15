import logging
import decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import UserProfile, Event, Participation, Transaction, SiteSettings
from .forms import CustomUserCreationForm, EventForm, RechargeForm, AdminRechargeForm

logger = logging.getLogger(__name__)


def _ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def home(request):
    logger.info(f"Home page accessed by {request.user}")
    upcoming_events = Event.objects.filter(date__gte=timezone.now())[:6]
    default_price = SiteSettings.get_default_price()
    context = {
        'upcoming_events': upcoming_events,
        'event_price': default_price,
    }
    return render(request, 'club/home.html', context)


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to the basketball club.')
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'club/register.html', {'form': form})


@login_required
def dashboard(request):
    logger.info(f"Dashboard accessed by user: {request.user.username} (staff={request.user.is_staff})")
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.user.is_staff:
        logger.info(f"Rendering admin dashboard for {request.user.username}")
        all_users = UserProfile.objects.select_related('user').all()[:20]
        recent_transactions = Transaction.objects.select_related('user').all()[:10]
        upcoming_events = Event.objects.filter(date__gte=timezone.now())[:10]
        total_balance = sum(u.balance for u in all_users)
        try:
            site_settings = SiteSettings.objects.get(name='default')
        except SiteSettings.DoesNotExist:
            site_settings = None
        context = {
            'balance': profile.balance,
            'all_users': all_users,
            'recent_transactions': recent_transactions,
            'upcoming_events': upcoming_events,
            'total_balance': total_balance,
            'site_settings': site_settings,
        }
        return render(request, 'club/admin_dashboard.html', context)

    upcoming_events = Event.objects.filter(date__gte=timezone.now()).exclude(
        participations__user=request.user,
        participations__status='registered'
    )[:5]
    my_events = Event.objects.filter(
        participations__user=request.user,
        participations__status='registered',
        date__gte=timezone.now()
    )[:5]
    default_price = SiteSettings.get_default_price()
    context = {
        'balance': profile.balance,
        'upcoming_events': upcoming_events,
        'my_events': my_events,
        'event_price': default_price,
    }
    return render(request, 'club/dashboard.html', context)


@login_required
def recharge(request):
    if request.method == 'POST':
        form = RechargeForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            with transaction.atomic():
                profile = _ensure_profile(request.user)
                profile.balance += amount
                profile.save(update_fields=['balance'])
                Transaction.objects.create(
                    user=request.user,
                    transaction_type='recharge',
                    amount=amount,
                    description=f'Account recharge: {amount}EUR'
                )
            messages.success(request, f'Successfully recharged {amount}EUR')
            return redirect('dashboard')
    else:
        form = RechargeForm()
    return render(request, 'club/recharge.html', {'form': form})


@login_required
def admin_recharge(request):
    if not request.user.is_staff:
        logger.warning(f"Non-admin user {request.user.username} attempted to access admin recharge")
        messages.error(request, 'Only administrators can access this page.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = AdminRechargeForm(request.POST)
        if form.is_valid():
            user_id = form.cleaned_data['user_id']
            amount = form.cleaned_data['amount']
            target_user = User.objects.filter(id=user_id, is_staff=False).first()
            if target_user is None:
                messages.error(request, 'Target member does not exist.')
                return redirect('admin_recharge')
            with transaction.atomic():
                profile = _ensure_profile(target_user)
                profile.balance += amount
                profile.save(update_fields=['balance'])
                Transaction.objects.create(
                    user=target_user,
                    transaction_type='recharge',
                    amount=amount,
                    description=f'Admin recharge by {request.user.username}'
                )
            logger.info(f"Admin {request.user.username} recharged {amount}EUR to user {target_user.username}")
            messages.success(request, f'Successfully recharged {amount}EUR to {target_user.username}')
            return redirect('dashboard')
    else:
        form = AdminRechargeForm()

    users = User.objects.filter(is_staff=False).select_related('profile')
    recharge_transactions = Transaction.objects.filter(
        transaction_type='recharge',
        description__startswith='Admin recharge by '
    ).select_related('user').order_by('-created_at')[:20]

    return render(request, 'club/admin_recharge.html', {
        'form': form,
        'users': users,
        'recharge_transactions': recharge_transactions,
    })


@login_required
@require_POST
def update_admin_recharge(request, transaction_id):
    if not request.user.is_staff:
        messages.error(request, 'Only administrators can update recharges.')
        return redirect('dashboard')

    recharge_tx = get_object_or_404(
        Transaction,
        id=transaction_id,
        transaction_type='recharge',
    )
    if not recharge_tx.description.startswith('Admin recharge by '):
        messages.error(request, 'Only manual admin recharges can be updated.')
        return redirect('admin_recharge')

    amount_raw = request.POST.get('amount', '').strip()
    try:
        new_amount = decimal.Decimal(amount_raw)
    except decimal.InvalidOperation:
        messages.error(request, 'Amount is invalid.')
        return redirect('admin_recharge')
    if new_amount <= 0:
        messages.error(request, 'Amount must be greater than 0.')
        return redirect('admin_recharge')

    with transaction.atomic():
        old_amount = recharge_tx.amount
        delta = new_amount - old_amount
        profile = _ensure_profile(recharge_tx.user)
        if profile.balance + delta < 0:
            messages.error(
                request,
                f'Cannot update: {recharge_tx.user.username} balance is too low for this change.',
            )
            return redirect('admin_recharge')
        profile.balance += delta
        profile.save(update_fields=['balance'])
        recharge_tx.amount = new_amount
        recharge_tx.save(update_fields=['amount'])

    messages.success(
        request,
        f'Updated recharge #{recharge_tx.id}: {old_amount}EUR -> {new_amount}EUR.',
    )
    return redirect('admin_recharge')


@login_required
@require_POST
def delete_admin_recharge(request, transaction_id):
    if not request.user.is_staff:
        messages.error(request, 'Only administrators can delete recharges.')
        return redirect('dashboard')

    recharge_tx = get_object_or_404(
        Transaction,
        id=transaction_id,
        transaction_type='recharge',
    )
    if not recharge_tx.description.startswith('Admin recharge by '):
        messages.error(request, 'Only manual admin recharges can be deleted.')
        return redirect('admin_recharge')

    with transaction.atomic():
        profile = _ensure_profile(recharge_tx.user)
        if profile.balance < recharge_tx.amount:
            messages.error(
                request,
                f'Cannot delete: {recharge_tx.user.username} balance is lower than {recharge_tx.amount}EUR.',
            )
            return redirect('admin_recharge')
        profile.balance -= recharge_tx.amount
        profile.save(update_fields=['balance'])
        recharge_tx.delete()

    messages.success(request, 'Recharge record deleted successfully.')
    return redirect('admin_recharge')


@login_required
def history(request):
    transactions = Transaction.objects.filter(user=request.user)
    return render(request, 'club/history.html', {'transactions': transactions})


@login_required
def event_list(request):
    events = Event.objects.filter(date__gte=timezone.now())
    user_participations = Participation.objects.filter(
        user=request.user,
        status='registered'
    ).values_list('event_id', flat=True)
    default_price = SiteSettings.get_default_price()
    return render(request, 'club/event_list.html', {
        'events': events,
        'user_participations': list(user_participations),
        'event_price': default_price,
    })


@login_required
def join_event(request, event_id):
    logger.info(f"User {request.user.username} attempting to join event {event_id}")
    event = get_object_or_404(Event, id=event_id)
    event_price = decimal.Decimal(event.event_price)

    if event.date < timezone.now():
        messages.error(request, 'This event has already passed.')
        return redirect('event_list')

    if event.is_full:
        messages.error(request, 'This event is full.')
        return redirect('event_list')

    with transaction.atomic():
        profile = _ensure_profile(request.user)
        participation = Participation.objects.filter(user=request.user, event=event).first()

        if participation and participation.status == 'registered':
            messages.warning(request, 'You are already registered for this event.')
            return redirect('event_list')

        if profile.balance < event_price:
            messages.error(request, f'Insufficient balance. You need at least {event_price}EUR to join.')
            return redirect('recharge')

        profile.balance -= event_price
        profile.save(update_fields=['balance'])

        if participation:
            participation.status = 'registered'
            participation.save(update_fields=['status'])
        else:
            Participation.objects.create(user=request.user, event=event, status='registered')

        Transaction.objects.create(
            user=request.user,
            transaction_type='event_fee',
            amount=event_price,
            description=f'Event: {event.title}',
            event=event
        )

    logger.info(f"User {request.user.username} joined event {event.title}, deducted {event_price}EUR")
    messages.success(request, f'Successfully joined {event.title}! {event_price}EUR has been deducted.')
    return redirect('event_list')


@login_required
def leave_event(request, event_id):
    logger.info(f"User {request.user.username} attempting to leave event {event_id}")
    event = get_object_or_404(Event, id=event_id)
    event_price = decimal.Decimal(event.event_price)

    participation = Participation.objects.filter(
        user=request.user,
        event=event,
        status='registered'
    ).first()

    if not participation:
        messages.warning(request, 'You are not registered for this event.')
        return redirect('event_list')

    if event.date < timezone.now():
        messages.error(request, 'Cannot leave past events.')
        return redirect('event_list')

    with transaction.atomic():
        participation.status = 'cancelled'
        participation.save(update_fields=['status'])

        profile = _ensure_profile(request.user)
        profile.balance += event_price
        profile.save(update_fields=['balance'])

        Transaction.objects.create(
            user=request.user,
            transaction_type='refund',
            amount=event_price,
            description=f'Refund for cancelled: {event.title}',
            event=event
        )

    messages.success(request, f'Successfully left {event.title}. {event_price}EUR has been refunded.')
    return redirect('event_list')


@login_required
def create_event(request):
    if not request.user.is_staff:
        messages.error(request, 'Only administrators can create events.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, f'Event "{event.title}" created successfully!')
            return redirect('event_list')
    else:
        form = EventForm()
    return render(request, 'club/create_event.html', {'form': form})


@login_required
def event_participants(request, event_id):
    if not request.user.is_staff:
        messages.error(request, 'Only administrators can view participant lists.')
        return redirect('dashboard')

    event = get_object_or_404(Event, id=event_id)
    participants = Participation.objects.filter(event=event, status='registered').select_related('user')
    return render(request, 'club/event_participants.html', {
        'event': event,
        'participants': participants,
    })


@login_required
def api_events(request):
    events = Event.objects.filter(date__gte=timezone.now())
    data = [{
        'id': e.id,
        'title': e.title,
        'start': e.date.isoformat(),
        'location': e.location,
        'participants': e.participant_count,
        'max': e.max_participants,
    } for e in events]
    return JsonResponse(data, safe=False)
