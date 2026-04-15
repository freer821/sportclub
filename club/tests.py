from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Event, Participation, Transaction, UserProfile


class RegistrationTests(TestCase):
    def test_register_creates_single_profile(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newmember',
                'email': 'newmember@example.com',
                'first_name': 'New',
                'last_name': 'Member',
                'password1': 'StrongPass12345',
                'password2': 'StrongPass12345',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='newmember')
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)


class EventFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='player', password='StrongPass12345')
        self.client.login(username='player', password='StrongPass12345')
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.balance = Decimal('20.00')
        self.profile.save(update_fields=['balance'])
        self.event = Event.objects.create(
            title='Weekend Match',
            description='test',
            location='Gym',
            date=timezone.now() + timezone.timedelta(days=1),
            max_participants=20,
            price=Decimal('5.00'),
        )

    def test_leave_event_saves_cancelled_status(self):
        Participation.objects.create(user=self.user, event=self.event, status='registered')
        self.profile.balance = Decimal('10.00')
        self.profile.save(update_fields=['balance'])

        response = self.client.get(reverse('leave_event', args=[self.event.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        participation = Participation.objects.get(user=self.user, event=self.event)
        self.assertEqual(participation.status, 'cancelled')
        self.assertEqual(self.profile.balance, Decimal('15.00'))
        self.assertEqual(
            Transaction.objects.filter(user=self.user, event=self.event, transaction_type='refund').count(),
            1,
        )

    def test_rejoin_after_cancelled_participation(self):
        Participation.objects.create(user=self.user, event=self.event, status='cancelled')

        response = self.client.get(reverse('join_event', args=[self.event.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        participation = Participation.objects.get(user=self.user, event=self.event)
        self.assertEqual(participation.status, 'registered')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.balance, Decimal('15.00'))
        self.assertEqual(
            Transaction.objects.filter(user=self.user, event=self.event, transaction_type='event_fee').count(),
            1,
        )


class AdminRechargeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        self.member = User.objects.create_user(username='member', password='StrongPass12345')
        self.client.login(username='admin', password='StrongPass12345')

    def test_admin_recharge_invalid_user_id(self):
        response = self.client.post(
            reverse('admin_recharge'),
            {'user_id': 999999, 'amount': '10.00'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_legacy_admin_recharge_url_is_supported(self):
        response = self.client.get('/admin/recharge/', follow=True)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_update_manual_recharge(self):
        member_profile = UserProfile.objects.get(user=self.member)
        member_profile.balance = Decimal('20.00')
        member_profile.save(update_fields=['balance'])
        tx = Transaction.objects.create(
            user=self.member,
            transaction_type='recharge',
            amount=Decimal('10.00'),
            description=f'Admin recharge by {self.admin.username}',
        )

        response = self.client.post(
            reverse('update_admin_recharge', args=[tx.id]),
            {'amount': '13.00'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        member_profile.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(member_profile.balance, Decimal('23.00'))
        self.assertEqual(tx.amount, Decimal('13.00'))

    def test_admin_can_delete_manual_recharge(self):
        member_profile = UserProfile.objects.get(user=self.member)
        member_profile.balance = Decimal('15.00')
        member_profile.save(update_fields=['balance'])
        tx = Transaction.objects.create(
            user=self.member,
            transaction_type='recharge',
            amount=Decimal('10.00'),
            description=f'Admin recharge by {self.admin.username}',
        )

        response = self.client.post(reverse('delete_admin_recharge', args=[tx.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        member_profile.refresh_from_db()
        self.assertEqual(member_profile.balance, Decimal('5.00'))
        self.assertFalse(Transaction.objects.filter(id=tx.id).exists())
