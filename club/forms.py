from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime
from .models import Event, Transaction


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user


class EventForm(forms.ModelForm):
    event_date = forms.DateField(
        label='活动日期',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    start_time = forms.TimeField(
        label='开始时间',
        widget=forms.TimeInput(attrs={'type': 'time'})
    )
    end_time = forms.TimeField(
        label='结束时间',
        widget=forms.TimeInput(attrs={'type': 'time'})
    )

    class Meta:
        model = Event
        fields = ['title', 'description', 'location']

    def clean(self):
        cleaned_data = super().clean()
        event_date = cleaned_data.get('event_date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if event_date and start_time and end_time and end_time <= start_time:
            self.add_error('end_time', '结束时间必须晚于开始时间。')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        event_date = self.cleaned_data['event_date']
        start_time = self.cleaned_data['start_time']
        end_time = self.cleaned_data['end_time']

        start_dt = datetime.combine(event_date, start_time)
        end_dt = datetime.combine(event_date, end_time)
        tz = timezone.get_current_timezone()
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)

        instance.date = start_dt
        instance.end_time = end_dt
        instance.price = None

        if commit:
            instance.save()
        return instance


class RechargeForm(forms.Form):
    amount = forms.DecimalField(
        label='充值金额',
        max_digits=10,
        decimal_places=2,
        min_value=1.0,
    )
    source = forms.ChoiceField(
        label='充值渠道',
        choices=Transaction.RECHARGE_SOURCE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    note = forms.CharField(
        label='备注',
        required=False,
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': '可填写转账单号、付款说明等',
            }
        ),
    )


class AdminRechargeForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput())
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=1.0)
    source = forms.ChoiceField(
        choices=Transaction.RECHARGE_SOURCE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    recharge_time = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text='留空则使用当前时间'
    )
