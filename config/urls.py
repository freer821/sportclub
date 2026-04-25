from django.urls import path, include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf.urls.i18n import i18n_patterns
from club import views

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

urlpatterns += i18n_patterns(
    path('admin/recharge/', views.admin_recharge, name='admin_recharge_legacy'),
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.member_profile, name='member_profile'),
    path('profile/check-in-qr.svg', views.member_checkin_qr_svg, name='member_checkin_qr_svg'),
    path('recharge/', views.recharge, name='recharge'),
    path('check-in/', views.qr_checkin, name='qr_checkin'),
    path('admin/members/', views.admin_members, name='admin_members'),
    path('admin/members/<int:user_id>/', views.admin_member_edit, name='admin_member_edit'),
    path('admin/members/<int:user_id>/check-in-qr.svg', views.admin_member_checkin_qr_svg, name='admin_member_checkin_qr_svg'),
    path('admin/recharge/', views.admin_recharge, name='admin_recharge'),
    path('admin/fees/', views.admin_fee_management, name='admin_fee_management'),
    path('admin/recharge/<int:user_id>/quick/', views.quick_recharge, name='quick_recharge'),
    path('admin/recharge/<int:transaction_id>/approve/', views.approve_admin_recharge, name='approve_admin_recharge'),
    path('admin/recharge/<int:transaction_id>/update/', views.update_admin_recharge, name='update_admin_recharge'),
    path('admin/recharge/<int:transaction_id>/delete/', views.delete_admin_recharge, name='delete_admin_recharge'),
    path('admin/events/', views.admin_events, name='admin_events'),
    path('admin/events/<int:event_id>/delete/', views.admin_event_delete, name='admin_event_delete'),
    path('history/', views.history, name='history'),
    path('events/', views.event_list, name='event_list'),
    path('events/<int:event_id>/join/', views.join_event, name='join_event'),
    path('events/<int:event_id>/leave/', views.leave_event, name='leave_event'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/<int:event_id>/participants/', views.event_participants, name='event_participants'),
    path('api/events/', views.api_events, name='api_events'),
    path('admin/', admin.site.urls),
    prefix_default_language=False,
)
