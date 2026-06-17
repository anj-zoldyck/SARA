from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # --- Auth ---
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('check-session/', views.check_session, name='check_session'),

    # --- MSWDO Dashboard ---
    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),

    # --- Barangay Accounts ---
    path('mswdo/barangay-accounts/', views.barangay_accounts, name='barangay_accounts'),
    path('mswdo/barangay-accounts/create/', views.create_barangay, name='create_barangay'),
    path('mswdo/barangay-accounts/<int:user_id>/edit/', views.edit_barangay, name='edit_barangay'),
    path('mswdo/barangay-accounts/<int:user_id>/deactivate/', views.deactivate_barangay, name='deactivate_barangay'),
    path('mswdo/barangay-accounts/<int:user_id>/activate/', views.activate_barangay, name='activate_barangay'),

    # --- Household / RFID browsing (MSWDO) ---
    path('mswdo/barangays/', views.barangay_list, name='barangay_list'),
    path('mswdo/barangays/<int:barangay_id>/zones/', views.barangay_zones, name='barangay_zones'),
    path('mswdo/zones/<int:zone_id>/households/', views.zone_households, name='zone_households'),
    path('mswdo/households/<int:household_id>/', views.household_info, name='household_info'),
    path('mswdo/families/<int:family_id>/members/', views.family_members, name='family_members'),
    path('mswdo/families/<int:family_id>/deactivate-rfid/', views.deactivate_rfid, name='deactivate_rfid'),

    # --- RFID ---
    path('mswdo/rfid/overview/', views.rfid_overview, name='rfid_overview'),
    path('mswdo/rfid/register/', views.register_rfid, name='register_rfid'),
    path('mswdo/rfid/register/<int:family_id>/', views.register_rfid, name='register_rfid_family'),
    path('mswdo/rfid/scan/', views.scan_rfid, name='scan_rfid'),
    path('mswdo/rfid/monitoring/', views.rfid_claim_monitoring, name='rfid_claim_monitoring'),
    path('mswdo/rfid/live-claims/', views.rfid_live_claims, name='rfid_live_claims'),

    # --- Aid Schedule ---
    path('mswdo/schedule/set/', views.set_aid_schedule, name='set_aid_schedule'),
    path('mswdo/schedule/status/', views.schedule_status, name='schedule_status'),

    # --- Aid Monitoring (FIXED: use assistance_id instead of aid_type string) ---
    path('mswdo/aid/', views.aid_type_list, name='aid_type_list'),
    path('mswdo/aid/<int:assistance_id>/barangays/', views.aid_barangay_list, name='aid_barangay_list'),
    path('mswdo/aid/<int:assistance_id>/barangays/<int:barangay_id>/', views.aid_barangay_detail, name='aid_barangay_detail'),

    # --- Reports & Analytics ---
    path('mswdo/reports/', views.aid_reports, name='aid_reports'),
    path('mswdo/analytics/', views.analytics, name='analytics'),

    # --- Program Management (NEW) ---
    path('mswdo/programs/', views.program_list, name='program_list'),
    path('mswdo/programs/add/', views.add_program, name='add_program'),
    path('mswdo/programs/<int:program_id>/edit/', views.edit_program, name='edit_program'),
    path('mswdo/programs/<int:program_id>/toggle/', views.toggle_program, name='toggle_program'),
    path('mswdo/programs/<int:program_id>/aid-categories/add/', views.add_aid_category, name='add_aid_category'),
    path('mswdo/programs/assistance/add/', views.add_assistance, name='add_assistance'),
    path('mswdo/programs/assistance/<int:assistance_id>/toggle/', views.toggle_assistance, name='toggle_assistance'),
    path('mswdo/programs/assistance/<int:assistance_id>/edit/', views.edit_assistance, name='edit_assistance'),

    # --- AJAX ---
    path('ajax/get-family-members/', views.get_family_members, name='get_family_members'),
    path('ajax/get-aid-categories/', views.get_aid_categories, name='get_aid_categories'),

    # --- Barangay Dashboard ---
    path('barangay/dashboard/', views.barangay_dashboard, name='barangay_dashboard'),
    path('barangay/zones/<int:zone_id>/', views.zone_detail, name='zone_detail'),
    path('barangay/zones/<int:zone_id>/households/add/', views.add_household, name='add_household'),
    path('barangay/households/<int:household_id>/', views.household_detail, name='household_detail'),
    path('barangay/households/<int:household_id>/families/add/', views.add_family, name='add_family'),
    path('barangay/families/<int:family_id>/', views.family_detail, name='family_detail'),
    path('barangay/families/<int:family_id>/members/add/', views.add_family_member, name='add_family_member'),
    path('barangay/members/<int:member_id>/edit/', views.edit_family_member, name='edit_family_member'),
    path('barangay/schedule-status/', views.barangay_schedule_status, name='barangay_schedule_status'),
    path('barangay/analytics/', views.barangay_analytics, name='barangay_analytics'),

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