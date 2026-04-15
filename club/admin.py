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
    list_display = ['user', 'balance']
    search_fields = ['user__username', 'user__email']
    list_filter = ['balance']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'location', 'max_participants', 'participant_count', 'price', 'created_by']
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
    list_display = ['user', 'transaction_type', 'amount', 'description', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__username', 'description']
    date_hierarchy = 'created_at'