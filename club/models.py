from django.db import models
from django.contrib.auth.models import User
from django.conf import settings


class SiteSettings(models.Model):
    name = models.CharField(max_length=100, default='default')
    default_event_price = models.DecimalField(max_digits=10, decimal_places=2, default=2.5)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.name

    @staticmethod
    def get_default_price():
        try:
            return SiteSettings.objects.get(name='default').default_event_price
        except SiteSettings.DoesNotExist:
            return getattr(settings, 'DEFAULT_EVENT_PRICE', 2.5)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.user.username}'s profile"


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=300)
    date = models.DateTimeField()
    max_participants = models.IntegerField(default=30)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.title} - {self.date.strftime('%Y-%m-%d %H:%M')}"

    @property
    def participant_count(self):
        return self.participations.filter(status='registered').count()

    @property
    def is_full(self):
        return self.participant_count >= self.max_participants

    @property
    def event_price(self):
        if self.price is not None:
            return self.price
        return SiteSettings.get_default_price()


class Participation(models.Model):
    STATUS_CHOICES = [
        ('registered', 'Registered'),
        ('cancelled', 'Cancelled'),
        ('attended', 'Attended'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='participations')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='registered')
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'event']

    def __str__(self):
        return f"{self.user.username} - {self.event.title}"


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('recharge', 'Recharge'),
        ('event_fee', 'Event Fee'),
        ('refund', 'Refund'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - {self.amount}EUR"
