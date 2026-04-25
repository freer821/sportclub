from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime
from .models import Event, Transaction, UserProfile


def _input_css_class(field):
    widget = field.widget
    if isinstance(widget, forms.CheckboxInput):
        return None
    if isinstance(widget, (forms.Select, forms.SelectDateWidget)):
        return "form-select"
    return "form-control"


class MemberProfileFieldsMixin(forms.Form):
    first_name = forms.CharField(max_length=30, required=True, label="名字")
    last_name = forms.CharField(max_length=30, required=True, label="姓氏")
    email = forms.EmailField(required=True, label="邮箱")
    gender = forms.ChoiceField(
        choices=UserProfile.GENDER_CHOICES,
        required=False,
        label="性别",
    )
    date_of_birth = forms.DateField(
        required=False,
        label="出生日期",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    phone = forms.CharField(max_length=50, required=False, label="电话 / 手机")
    street_address = forms.CharField(
        max_length=255,
        required=False,
        label="街道与门牌号",
    )
    postal_code = forms.CharField(max_length=20, required=False, label="邮编")
    city = forms.CharField(max_length=100, required=False, label="城市")
    nationality = forms.CharField(max_length=100, required=False, label="国籍")
    membership_type = forms.ChoiceField(
        choices=UserProfile.MEMBERSHIP_TYPE_CHOICES,
        required=True,
        label="会员类型",
    )

    profile_field_names = [
        "gender",
        "date_of_birth",
        "phone",
        "street_address",
        "postal_code",
        "city",
        "nationality",
        "membership_type",
    ]

    def initialize_profile_fields(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["email"].initial = user.email
        for field_name in self.profile_field_names:
            self.fields[field_name].initial = getattr(profile, field_name)

    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            css_class = _input_css_class(field)
            if not css_class:
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()

    def save_profile(self, user):
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        for field_name in self.profile_field_names:
            setattr(profile, field_name, self.cleaned_data[field_name])
        if not profile.membership_start_date:
            profile.membership_start_date = timezone.localdate()
        profile.save()
        return profile


class CustomUserCreationForm(MemberProfileFieldsMixin, UserCreationForm):
    username = forms.CharField(max_length=150, required=True, label="用户名")
    password1 = forms.CharField(
        label="密码",
        strip=False,
        widget=forms.PasswordInput(),
    )
    password2 = forms.CharField(
        label="确认密码",
        strip=False,
        widget=forms.PasswordInput(),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

    field_order = [
        "username",
        "first_name",
        "last_name",
        "email",
        "gender",
        "date_of_birth",
        "phone",
        "street_address",
        "postal_code",
        "city",
        "nationality",
        "membership_type",
        "password1",
        "password2",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            self.save_profile(user)
        return user


class MemberProfileUpdateForm(MemberProfileFieldsMixin, forms.Form):
    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
        if not self.is_bound:
            self.initialize_profile_fields(user)

    def save(self):
        return self.save_profile(self.user)


class AdminMemberUpdateForm(MemberProfileFieldsMixin, forms.Form):
    username = forms.CharField(max_length=150, required=True, label="用户名")
    is_active = forms.BooleanField(required=False, label="启用会员")
    balance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label="账户余额",
    )
    membership_start_date = forms.DateField(
        required=False,
        label="入会日期",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    admin_note = forms.CharField(
        required=False,
        label="管理员备注",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    field_order = [
        "username",
        "email",
        "first_name",
        "last_name",
        "gender",
        "date_of_birth",
        "phone",
        "street_address",
        "postal_code",
        "city",
        "nationality",
        "membership_type",
        "membership_start_date",
        "balance",
        "admin_note",
        "is_active",
    ]

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
        if not self.is_bound:
            self.initialize_profile_fields(user)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            self.fields["username"].initial = user.username
            self.fields["is_active"].initial = user.is_active
            self.fields["balance"].initial = profile.balance
            self.fields["membership_start_date"].initial = profile.membership_start_date
            self.fields["admin_note"].initial = profile.admin_note

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.exclude(pk=self.user.pk).filter(username=username).exists():
            raise forms.ValidationError("该用户名已被使用。")
        return username

    def save(self):
        self.user.username = self.cleaned_data["username"]
        self.user.is_active = self.cleaned_data["is_active"]
        self.save_profile(self.user)

        profile = self.user.profile
        profile.balance = self.cleaned_data["balance"]
        profile.membership_start_date = (
            self.cleaned_data["membership_start_date"] or timezone.localdate()
        )
        profile.admin_note = self.cleaned_data["admin_note"]
        self.user.save()
        profile.save()
        return self.user, profile


class EventForm(forms.ModelForm):
    REPEAT_CHOICES = [
        ('none', '不重复'),
        ('weekly', '每周'),
        ('biweekly', '每两周'),
    ]
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
    repeat_mode = forms.ChoiceField(
        label='重复方式',
        choices=REPEAT_CHOICES,
        required=False,
        initial='none',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='可按固定周期连续创建多场活动',
    )
    repeat_count = forms.IntegerField(
        label='重复次数',
        min_value=1,
        max_value=12,
        required=False,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='填写总共要创建几场，例如 4 表示创建 4 场',
    )

    class Meta:
        model = Event
        fields = ['title', 'description', 'location']

    def clean(self):
        cleaned_data = super().clean()
        event_date = cleaned_data.get('event_date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        repeat_mode = cleaned_data.get('repeat_mode') or 'none'
        repeat_count = cleaned_data.get('repeat_count')

        if event_date and start_time and end_time and end_time <= start_time:
            self.add_error('end_time', '结束时间必须晚于开始时间。')
        if repeat_mode != 'none' and not repeat_count:
            self.add_error('repeat_count', '选择重复创建时，请填写重复次数。')

        return cleaned_data

    def build_datetimes(self):
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

        return start_dt, end_dt

    def save(self, commit=True):
        instance = super().save(commit=False)
        start_dt, end_dt = self.build_datetimes()
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


class QRCheckInForm(forms.Form):
    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        empty_label=None,
        label='活动',
    )

    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].queryset = events
        self.fields['event'].widget.attrs['class'] = 'form-select'
