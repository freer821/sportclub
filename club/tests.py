from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Event, Participation, Transaction, UserProfile
from club.forms import EventForm


class RegistrationTests(TestCase):
    def test_register_creates_single_profile(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newmember',
                'email': 'newmember@example.com',
                'first_name': 'New',
                'last_name': 'Member',
                'password1': 'simple1',
                'password2': 'simple1',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='newmember')
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)

    def test_register_allows_simple_password_when_length_requirement_is_met(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'easyuser',
                'email': 'easyuser@example.com',
                'first_name': 'Easy',
                'last_name': 'User',
                'password1': '123456',
                'password2': '123456',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='easyuser').exists())


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

    def test_member_recharge_creates_pending_request_without_updating_balance(self):
        self.client.logout()
        self.client.login(username='member', password='StrongPass12345')

        response = self.client.post(
            reverse('recharge'),
            {
                'amount': '18.00',
                'source': 'wechat',
                'note': '转账截图已提交',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        tx = Transaction.objects.get(user=self.member, transaction_type='recharge')
        member_profile = UserProfile.objects.get(user=self.member)
        self.assertEqual(tx.status, 'pending')
        self.assertEqual(tx.source, 'wechat')
        self.assertEqual(tx.note, '转账截图已提交')
        self.assertEqual(member_profile.balance, Decimal('0'))

    def test_admin_can_approve_pending_recharge_request(self):
        tx = Transaction.objects.create(
            user=self.member,
            transaction_type='recharge',
            amount=Decimal('18.00'),
            source='paypal',
            note='waiting for approval',
            status='pending',
            description='充值申请（PayPal）',
        )

        response = self.client.post(
            reverse('approve_admin_recharge', args=[tx.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        member_profile = UserProfile.objects.get(user=self.member)
        self.assertEqual(tx.status, 'approved')
        self.assertEqual(tx.approved_by, self.admin)
        self.assertEqual(member_profile.balance, Decimal('18.00'))

    def test_admin_can_update_pending_recharge_request_details(self):
        tx = Transaction.objects.create(
            user=self.member,
            transaction_type='recharge',
            amount=Decimal('12.00'),
            source='wechat',
            note='old note',
            status='pending',
            description='充值申请（WeChat）',
        )

        response = self.client.post(
            reverse('update_admin_recharge', args=[tx.id]),
            {
                'amount': '15.50',
                'source': 'cash',
                'note': 'paid in person',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        member_profile = UserProfile.objects.get(user=self.member)
        self.assertEqual(tx.amount, Decimal('15.50'))
        self.assertEqual(tx.source, 'cash')
        self.assertEqual(tx.note, 'paid in person')
        self.assertEqual(tx.status, 'pending')
        self.assertEqual(member_profile.balance, Decimal('0'))

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


class AdminDashboardStatsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        self.member1 = User.objects.create_user(username='member1', password='StrongPass12345')
        self.member2 = User.objects.create_user(username='member2', password='StrongPass12345')
        self.client.login(username='admin', password='StrongPass12345')

    def test_registered_member_count_excludes_admin_users(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['registered_member_count'], 2)
        self.assertTrue(all(not profile.user.is_staff for profile in response.context['all_users']))


class EventCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        self.client.login(username='admin', password='StrongPass12345')

    def test_event_form_does_not_expose_max_participants_or_price(self):
        form = EventForm()
        self.assertNotIn('max_participants', form.fields)
        self.assertNotIn('price', form.fields)
        self.assertIn('event_date', form.fields)
        self.assertIn('start_time', form.fields)
        self.assertIn('end_time', form.fields)

    def test_site_settings_admin_url_is_resolvable(self):
        self.assertEqual(reverse('admin:club_sitesettings_changelist'), '/admin/club/sitesettings/')

    def test_admin_can_create_event_with_date_start_and_end_time(self):
        response = self.client.post(
            reverse('create_event'),
            {
                'title': 'Evening Match',
                'description': 'training',
                'location': 'Main Gym',
                'event_date': date.today().isoformat(),
                'start_time': '18:00',
                'end_time': '20:00',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        event = Event.objects.get(title='Evening Match')
        self.assertEqual(timezone.localtime(event.date).strftime('%H:%M'), '18:00')
        self.assertEqual(timezone.localtime(event.end_time).strftime('%H:%M'), '20:00')
        self.assertEqual(event.max_participants, 30)
        self.assertIsNone(event.price)

    def test_admin_can_create_repeated_events(self):
        response = self.client.post(
            reverse('create_event'),
            {
                'title': 'Weekly Match',
                'description': 'repeat',
                'location': 'Main Gym',
                'event_date': date.today().isoformat(),
                'start_time': '18:00',
                'end_time': '20:00',
                'repeat_mode': 'weekly',
                'repeat_count': 3,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.filter(title='Weekly Match').count(), 3)


class UpcomingEventsTests(TestCase):
    def test_home_prefers_today_event_over_later_event(self):
        now = timezone.now()
        today_event = Event.objects.create(
            title='Today Match',
            description='today',
            location='Court A',
            date=now + timezone.timedelta(hours=1),
            end_time=now + timezone.timedelta(hours=3),
        )
        future_event = Event.objects.create(
            title='Future Match',
            description='future',
            location='Court C',
            date=now + timezone.timedelta(days=1),
            end_time=now + timezone.timedelta(days=1, hours=2),
        )

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['featured_event'].id, today_event.id)
        self.assertTrue(response.context['featured_event_is_today'])
        upcoming_ids = [event.id for event in response.context['upcoming_events']]
        self.assertEqual(upcoming_ids, [today_event.id])

    def test_home_falls_back_to_next_event_when_no_today_event(self):
        now = timezone.now()
        next_event = Event.objects.create(
            title='Next Match',
            description='future',
            location='Court A',
            date=now + timezone.timedelta(days=2),
            end_time=now + timezone.timedelta(days=2, hours=2),
        )

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['featured_event'].id, next_event.id)
        self.assertFalse(response.context['featured_event_is_today'])
        self.assertEqual([event.id for event in response.context['upcoming_events']], [next_event.id])

    def test_home_has_no_featured_event_when_no_upcoming_event_exists(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['featured_event'])
        self.assertFalse(response.context['featured_event_is_today'])
        self.assertEqual(response.context['upcoming_events'], [])

    def test_admin_dashboard_upcoming_events_include_ongoing(self):
        admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        now = timezone.now()
        ongoing = Event.objects.create(
            title='Ongoing Admin Match',
            description='ongoing',
            location='Court A',
            date=now - timezone.timedelta(minutes=30),
            end_time=now + timezone.timedelta(minutes=90),
        )
        self.client.login(username='admin', password='StrongPass12345')

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        upcoming_ids = [event.id for event in response.context['upcoming_events']]
        self.assertIn(ongoing.id, upcoming_ids)


class EventListTests(TestCase):
    def test_admin_event_list_does_not_show_join_actions(self):
        admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        event = Event.objects.create(
            title='Admin View Match',
            description='admin',
            location='Court A',
            date=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=2),
        )
        self.client.login(username='admin', password='StrongPass12345')

        response = self.client.get(reverse('event_list'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('join_event', args=[event.id]))
        self.assertContains(response, '详情')
