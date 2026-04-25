from django.contrib import admin
from .models import UserProfile, Event, Participation, Transaction, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['name', 'default_event_price']

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        if SiteSettings.objects.exists():
            return False
        return True


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'membership_type', 'city', 'phone', 'balance', 'profile_updated_at']
    search_fields = ['user__username', 'user__email', 'phone', 'city', 'nationality']
    list_filter = ['membership_type', 'gender', 'city']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'end_time', 'location', 'max_participants', 'participant_count', 'price', 'created_by']
    list_filter = ['date', 'created_by']
    search_fields = ['title', 'location']
    date_hierarchy = 'date'


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'status', 'registered_at']
    list_filter = ['status', 'event']
    search_fields = ['user__username', 'event__title']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction_type', 'amount', 'status', 'source', 'approved_by', 'created_at']
    list_filter = ['transaction_type', 'status', 'source', 'created_at']
    search_fields = ['user__username', 'description']
    date_hierarchy = 'created_at'
