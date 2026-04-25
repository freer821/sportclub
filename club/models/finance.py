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


class Transaction(models.Model):
    RECHARGE_SOURCE_CHOICES = [
        ('wechat', 'WeChat'),
        ('paypal', 'PayPal'),
        ('cash', '现金'),
        ('other', '其他'),
    ]
    RECHARGE_STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已批准'),
    ]
    TYPE_CHOICES = [
        ('recharge', 'Recharge'),
        ('event_fee', 'Event Fee'),
        ('refund', 'Refund'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200)
    source = models.CharField(
        max_length=20,
        choices=RECHARGE_SOURCE_CHOICES,
        blank=True,
        default='',
    )
    note = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=RECHARGE_STATUS_CHOICES,
        default='approved',
    )
    event = models.ForeignKey('Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_transactions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - {self.amount}EUR"


class EventFeeCharge(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SETTLED = "settled"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待补缴"),
        (STATUS_SETTLED, "已结清"),
        (STATUS_CANCELLED, "已取消"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_fee_charges")
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="fee_charges")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    note = models.TextField(blank=True, default="")
    payment_transaction = models.ForeignKey(
        "Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_fee_charges",
    )
    settled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settled_event_fee_charges",
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="unique_event_fee_charge")
        ]

    def __str__(self):
        return f"{self.user.username} - {self.event.title} - {self.status}"
