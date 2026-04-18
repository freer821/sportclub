from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=300)
    date = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
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
        from club.models.finance import SiteSettings
        return SiteSettings.get_default_price()

    @property
    def total_fee_amount(self):
        return Decimal(str(self.event_price)) * self.participant_count


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
