from django.urls import path, include
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
    path('recharge/', views.recharge, name='recharge'),
    path('member/recharge/', views.admin_recharge, name='admin_recharge'),
    path('member/recharge/<int:transaction_id>/update/', views.update_admin_recharge, name='update_admin_recharge'),
    path('member/recharge/<int:transaction_id>/delete/', views.delete_admin_recharge, name='delete_admin_recharge'),
    path('history/', views.history, name='history'),
    path('events/', views.event_list, name='event_list'),
    path('events/<int:event_id>/join/', views.join_event, name='join_event'),
    path('events/<int:event_id>/leave/', views.leave_event, name='leave_event'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/<int:event_id>/participants/', views.event_participants, name='event_participants'),
    path('api/events/', views.api_events, name='api_events'),
    prefix_default_language=False,
)
