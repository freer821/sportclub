from datetime import date

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    GENDER_MALE = "male"
    GENDER_FEMALE = "female"
    GENDER_DIVERSE = "diverse"
    GENDER_UNSPECIFIED = "unspecified"
    GENDER_CHOICES = [
        (GENDER_MALE, "男"),
        (GENDER_FEMALE, "女"),
        (GENDER_DIVERSE, "多元"),
        (GENDER_UNSPECIFIED, "未说明"),
    ]

    MEMBERSHIP_ADULT = "adult"
    MEMBERSHIP_CHILD = "child"
    MEMBERSHIP_FAMILY = "family"
    MEMBERSHIP_YOUNG_ADULT = "young_adult"
    MEMBERSHIP_TYPE_CHOICES = [
        (MEMBERSHIP_ADULT, "成年人"),
        (MEMBERSHIP_CHILD, "儿童"),
        (MEMBERSHIP_FAMILY, "家庭"),
        (MEMBERSHIP_YOUNG_ADULT, "青年/学生"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        default=GENDER_UNSPECIFIED,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    membership_type = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_TYPE_CHOICES,
        default=MEMBERSHIP_ADULT,
    )
    membership_start_date = models.DateField(default=date.today)
    admin_note = models.TextField(blank=True)
    profile_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile"
