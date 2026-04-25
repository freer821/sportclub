from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Event, EventFeeCharge, Participation, Transaction, UserProfile
from club.forms import EventForm
from club.services import build_checkin_token


class RegistrationTests(TestCase):
    def test_register_creates_single_profile(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newmember',
                'email': 'newmember@example.com',
                'first_name': 'New',
                'last_name': 'Member',
                'gender': 'male',
                'date_of_birth': '1995-04-03',
                'phone': '+49 151 123456',
                'street_address': 'Mainzer Landstr. 10',
                'postal_code': '60329',
                'city': 'Frankfurt',
                'nationality': 'China',
                'membership_type': 'adult',
                'password1': 'simple1',
                'password2': 'simple1',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='newmember')
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)
        self.assertEqual(profile.gender, 'male')
        self.assertEqual(profile.city, 'Frankfurt')
        self.assertEqual(profile.membership_type, 'adult')

    def test_register_allows_simple_password_when_length_requirement_is_met(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'easyuser',
                'email': 'easyuser@example.com',
                'first_name': 'Easy',
                'last_name': 'User',
                'gender': 'female',
                'date_of_birth': '1998-05-06',
                'phone': '0170123456',
                'street_address': 'Bockenheimer Landstr. 5',
                'postal_code': '60325',
                'city': 'Frankfurt',
                'nationality': 'Germany',
                'membership_type': 'young_adult',
                'password1': '123456',
                'password2': '123456',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='easyuser').exists())


class MemberProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            password='StrongPass12345',
            email='member@example.com',
            first_name='Old',
            last_name='Name',
        )
        self.client.login(username='member', password='StrongPass12345')

    def test_member_can_update_profile(self):
        response = self.client.post(
            reverse('member_profile'),
            {
                'first_name': 'New',
                'last_name': 'Member',
                'email': 'newmember@example.com',
                'gender': 'diverse',
                'date_of_birth': '2000-01-02',
                'phone': '+49 170 998877',
                'street_address': 'Europa-Allee 1',
                'postal_code': '60327',
                'city': 'Frankfurt',
                'nationality': 'China',
                'membership_type': 'family',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        profile = self.user.profile
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.email, 'newmember@example.com')
        self.assertEqual(profile.gender, 'diverse')
        self.assertEqual(profile.city, 'Frankfurt')
        self.assertEqual(profile.membership_type, 'family')

    def test_staff_user_is_redirected_away_from_member_profile_page(self):
        self.client.logout()
        admin = User.objects.create_user(
            username='admin',
            password='StrongPass12345',
            is_staff=True,
        )
        self.client.login(username='admin', password='StrongPass12345')

        response = self.client.get(reverse('member_profile'))

        self.assertRedirects(response, reverse('dashboard'))


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
        payment_tx = Transaction.objects.create(
            user=self.user,
            event=self.event,
            transaction_type='event_fee',
            amount=Decimal('5.00'),
            description='Event: Weekend Match',
        )
        EventFeeCharge.objects.create(
            user=self.user,
            event=self.event,
            amount=Decimal('5.00'),
            status=EventFeeCharge.STATUS_SETTLED,
            payment_transaction=payment_tx,
        )
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


class QRCheckInTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='qmember',
            password='StrongPass12345',
            first_name='QR',
            last_name='Member',
        )
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.balance = Decimal('25.00')
        self.profile.save(update_fields=['balance'])
        now = timezone.now()
        self.started_event = Event.objects.create(
            title='Started Match',
            description='ongoing',
            location='Gym A',
            date=now - timezone.timedelta(minutes=30),
            end_time=now + timezone.timedelta(hours=1),
            max_participants=20,
            price=Decimal('6.00'),
        )
        self.future_event = Event.objects.create(
            title='Future Match',
            description='future',
            location='Gym B',
            date=now + timezone.timedelta(hours=2),
            end_time=now + timezone.timedelta(hours=4),
            max_participants=20,
            price=Decimal('6.00'),
        )
        self.token = build_checkin_token(self.user)

    def test_qr_checkin_page_lists_started_events_only(self):
        response = self.client.get(reverse('qr_checkin'), {'token': self.token})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Started Match')
        self.assertNotContains(response, 'Future Match')

    def test_qr_checkin_creates_attended_participation_and_fee(self):
        response = self.client.post(
            reverse('qr_checkin'),
            {'token': self.token, 'event': self.started_event.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        participation = Participation.objects.get(user=self.user, event=self.started_event)
        self.profile.refresh_from_db()
        self.assertEqual(participation.status, Participation.STATUS_ATTENDED)
        self.assertEqual(self.profile.balance, Decimal('19.00'))
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user,
                event=self.started_event,
                transaction_type='event_fee',
            ).count(),
            1,
        )

    def test_qr_checkin_marks_existing_registration_without_duplicate_fee(self):
        Participation.objects.create(
            user=self.user,
            event=self.started_event,
            status=Participation.STATUS_REGISTERED,
        )
        Transaction.objects.create(
            user=self.user,
            event=self.started_event,
            transaction_type='event_fee',
            amount=Decimal('6.00'),
            description='Event: Started Match',
        )
        EventFeeCharge.objects.create(
            user=self.user,
            event=self.started_event,
            amount=Decimal('6.00'),
            status=EventFeeCharge.STATUS_SETTLED,
        )

        response = self.client.post(
            reverse('qr_checkin'),
            {'token': self.token, 'event': self.started_event.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        participation = Participation.objects.get(user=self.user, event=self.started_event)
        self.profile.refresh_from_db()
        self.assertEqual(participation.status, Participation.STATUS_ATTENDED)
        self.assertEqual(self.profile.balance, Decimal('25.00'))
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user,
                event=self.started_event,
                transaction_type='event_fee',
            ).count(),
            1,
        )

    def test_member_can_fetch_personal_checkin_qr_svg(self):
        self.client.login(username='qmember', password='StrongPass12345')

        response = self.client.get(reverse('member_checkin_qr_svg'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertIn('<svg', response.content.decode('utf-8'))

    def test_qr_checkin_allows_insufficient_balance_and_records_pending_fee(self):
        self.profile.balance = Decimal('2.00')
        self.profile.save(update_fields=['balance'])

        response = self.client.post(
            reverse('qr_checkin'),
            {'token': self.token, 'event': self.started_event.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        participation = Participation.objects.get(user=self.user, event=self.started_event)
        charge = EventFeeCharge.objects.get(
            user=self.user,
            event=self.started_event,
        )
        self.assertEqual(participation.status, Participation.STATUS_ATTENDED)
        self.assertEqual(self.profile.balance, Decimal('2.00'))
        self.assertEqual(
            Transaction.objects.filter(
                user=self.user,
                event=self.started_event,
                transaction_type='event_fee',
            ).count(),
            0,
        )
        self.assertEqual(charge.status, EventFeeCharge.STATUS_PENDING)
        self.assertIn('待补缴 6.00EUR', charge.note)

    def test_qr_checkin_prefers_today_event_over_older_ongoing_event(self):
        older_ongoing = Event.objects.create(
            title='Yesterday Match',
            description='older',
            location='Gym C',
            date=timezone.now() - timezone.timedelta(days=1, hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=2),
            max_participants=20,
            price=Decimal('4.00'),
        )

        response = self.client.get(reverse('qr_checkin'), {'token': self.token})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_event'].id, self.started_event.id)
        self.assertNotEqual(response.context['selected_event'].id, older_ongoing.id)


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

    def test_admin_approved_recharge_settles_pending_event_fee(self):
        EventFeeCharge.objects.create(
            user=self.member,
            event=Event.objects.create(
                title='Training',
                description='fee',
                location='Court A',
                date=timezone.now(),
                end_time=timezone.now() + timezone.timedelta(hours=2),
            ),
            amount=Decimal('6.00'),
            status=EventFeeCharge.STATUS_PENDING,
            note='余额不足，签到已记录，待补缴 6.00EUR。',
        )
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
        member_profile = UserProfile.objects.get(user=self.member)
        event_fee_charge = EventFeeCharge.objects.get(user=self.member)
        event_fee_tx = Transaction.objects.get(
            user=self.member,
            transaction_type='event_fee',
        )
        self.assertEqual(member_profile.balance, Decimal('12.00'))
        self.assertEqual(event_fee_charge.status, EventFeeCharge.STATUS_SETTLED)
        self.assertEqual(event_fee_tx.status, 'approved')
        self.assertEqual(event_fee_tx.amount, Decimal('6.00'))

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


class AdminFeeManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='StrongPass12345', is_staff=True)
        self.member = User.objects.create_user(username='member', password='StrongPass12345')
        self.event = Event.objects.create(
            title='Revenue Match',
            description='fees',
            location='Court A',
            date=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=2),
            price=Decimal('8.00'),
        )
        self.client.login(username='admin', password='StrongPass12345')

    def test_admin_fee_management_shows_pending_and_approved_fees(self):
        pending_event = Event.objects.create(
            title='Pending Match',
            description='fees',
            location='Court B',
            date=timezone.now() + timezone.timedelta(days=2),
            end_time=timezone.now() + timezone.timedelta(days=2, hours=2),
            price=Decimal('8.00'),
        )
        EventFeeCharge.objects.create(
            user=self.member,
            event=pending_event,
            amount=Decimal('8.00'),
            status=EventFeeCharge.STATUS_PENDING,
            note='待补缴',
        )
        approved_tx = Transaction.objects.create(
            user=self.member,
            event=self.event,
            transaction_type='event_fee',
            amount=Decimal('8.00'),
            status='approved',
            description='Event: Revenue Match',
        )
        EventFeeCharge.objects.create(
            user=self.member,
            event=self.event,
            amount=Decimal('8.00'),
            status=EventFeeCharge.STATUS_SETTLED,
            payment_transaction=approved_tx,
        )

        response = self.client.get(reverse('admin_fee_management'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '待补缴扣费')
        self.assertContains(response, '最近已扣费记录')
        self.assertContains(response, 'Revenue Match')
        self.assertEqual(response.context['approved_fee_total'], Decimal('8.00'))
        self.assertEqual(response.context['pending_fee_total'], Decimal('8.00'))


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


class ApiEventsTests(TestCase):
    def test_api_events_returns_existing_events_for_calendar(self):
        past_event = Event.objects.create(
            title='Past Match',
            description='already created',
            location='Gym',
            date=timezone.now() - timezone.timedelta(days=2),
            end_time=timezone.now() - timezone.timedelta(days=2) + timezone.timedelta(hours=2),
            max_participants=20,
            price=Decimal('5.00'),
        )
        future_event = Event.objects.create(
            title='Future Match',
            description='scheduled',
            location='Gym',
            date=timezone.now() + timezone.timedelta(days=2),
            end_time=timezone.now() + timezone.timedelta(days=2, hours=2),
            max_participants=20,
            price=Decimal('5.00'),
        )

        response = self.client.get(reverse('api_events'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item['id'] for item in payload}
        self.assertIn(past_event.id, ids)
        self.assertIn(future_event.id, ids)


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
