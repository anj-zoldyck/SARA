from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('check-session/', views.check_session, name='check_session'),

    path('mswdo/users/', views.user_accounts, name='user_accounts'),
    path('mswdo/users/create/', views.create_user, name='create_user'),
    path('mswdo/users/<int:user_id>/deactivate/', views.deactivate_user, name='deactivate_user'),
    path('mswdo/users/<int:user_id>/activate/', views.activate_user_account, name='activate_user_account'),
    
    path('force-password-change/', views.force_password_change, name='force_password_change'),

    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='password-reset/password_reset.html',
        email_template_name='password-reset/password_reset_email.txt',
        html_email_template_name='password-reset/password_reset_email.html',
        subject_template_name='password_reset_subject.txt',
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password-reset/password_reset_done.html'), name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password-reset/password_reset_confirm.html', success_url='/password-reset/complete/'), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='password-reset/password_reset_complete.html'), name='password_reset_complete'),

    path('settings/', views.settings_view, name='settings'),
    path('settings/photo/', views.update_profile_photo, name='update_profile_photo'),
    path('settings/photo/remove/', views.remove_profile_photo, name='remove_profile_photo'),
]
