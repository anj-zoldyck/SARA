from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.landing_page, name='landing'),

    #MSWDO URLs
    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),
    path('mswdo/barangay/create/', views.create_barangay, name='create_barangay'),
    path('mswdo/barangay/deactivate/<int:user_id>/', views.deactivate_barangay, name='deactivate_barangay'),

    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),
    path('mswdo/households/', views.household_list, name='household_list'),
    path('mswdo/families/', views.family_list, name='family_list'),
    path('mswdo/rfid-overview/', views.rfid_overview, name='rfid_overview'),

    path('mswdo/barangay-accounts/', views.barangay_accounts, name='barangay_accounts'),
    path('mswdo/barangay-accounts/<int:user_id>/edit/', views.edit_barangay, name='edit_barangay'),
    path('mswdo/barangay-accounts/<int:user_id>/deactivate/', views.deactivate_barangay, name='deactivate_barangay'),
    path('mswdo/barangay-accounts/<int:user_id>/activate/', views.activate_barangay, name='activate_barangay'),
    #path('mswdo/set-aid-of-the-day/', views.set_aid_of_the_day, name='set_aid_of_the_day'),
    path('mswdo/set-aid-schedule/', views.set_aid_schedule, name='set_aid_schedule'),


    # MSWDO Aid Monitoring
    path('mswdo/aids/', views.aid_type_list, name='aid_type_list'),
    path('mswdo/aids/<str:aid_type>/', views.aid_barangay_list, name='aid_barangay_list'),
    path('mswdo/aids/<str:aid_type>/barangay/<int:barangay_id>/',views.aid_barangay_detail, name='aid_barangay_detail'),
    path('mswdo/monitoring/', views.rfid_claim_monitoring, name='rfid_claim_monitoring'),

    # List barangays for a given aid type
    path('mswdo/aids/<str:aid_type>/', views.aid_list, name='aid_list'),
    # Show households in a barangay for a given aid type
    path('mswdo/aids/<int:barangay_id>/<str:aid_type>/', views.aid_barangay_detail, name='aid_barangay_detail'),
    path('mswdo/scan/', views.scan_rfid, name='scan_rfid'),

    #Register RFID to Family
    path('mswdo/rfid/register/', views.register_rfid, name='register_rfid'),
    path('mswdo/rfid/register/<int:family_id>/', views.register_rfid, name='register_rfid'),

    # RFID Deactivate
    path('mswdo/rfid/deactivate/<int:family_id>/', views.deactivate_rfid, name='deactivate_rfid'),

    #AJAX URLs
    path('ajax/get_family_members/', views.get_family_members, name='get_family_members'),

    #List of Barangays
    path('mswdo/barangays/', views.barangay_list, name='barangay_list'),
    path('mswdo/barangays/<int:barangay_id>/zones/', views.barangay_zones,name='barangay_zones'),
    path('mswdo/zones/<int:zone_id>/households/', views.zone_households, name='zone_households'),
    path('mswdo/households/<int:household_id>/families/', views.household_info, name='household_info'),
    path('mswdo/families/<int:family_id>/members/', views.family_members, name='family_members'),

    # Analytics
    path('mswdo/analytics/', views.analytics, name='analytics'),

    # Aid Reports
   path('mswdo/reports/', views.aid_reports, name='aid_reports'),





    #Barangay URLs
    path('dashboard/', views.barangay_dashboard, name='barangay_dashboard'),

    path('zone/<int:zone_id>/', views.zone_detail, name='zone_detail'),
    path('zone/<int:zone_id>/add-household/', views.add_household, name='add_household'),

    path('household/<int:household_id>/', views.household_detail, name='household_detail'),
    path('household/<int:household_id>/add-family/', views.add_family, name='add_family'),

    path('family/<int:family_id>/', views.family_detail, name='family_detail'),
    path('family/<int:family_id>/add-member/', views.add_family_member, name='add_family_member'),

    path('member/<int:member_id>/edit/', views.edit_family_member, name='edit_family_member'),

    # check session URL for AJAX
    path('check-session/', views.check_session, name='check_session'),


    # ── Password Reset Flow ──────────────────────────────
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='password-reset/password_reset.html',

            # Plain text fallback email
            email_template_name='password-reset/password_reset_email.txt',

            # HTML email
            html_email_template_name='password-reset/password_reset_email.html',

            subject_template_name='password_reset_subject.txt',

            success_url='/password-reset/done/',
        ),
        name='password_reset',
    ),
 
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='password-reset/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
 
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='password-reset/password_reset_confirm.html',
            success_url='/password-reset/complete/',
        ),
        name='password_reset_confirm',
    ),
 
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='password-reset/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # Schedule Status API for AJAX
    path('schedule-status/', views.schedule_status, name='schedule_status'),

]
