from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/schedule-distribution/', views.schedule_distribution, name='schedule_distribution'),
    path('mswdo/schedule/<int:schedule_id>/generate/', views.generate_beneficiaries, name='generate_beneficiaries'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/', views.review_beneficiaries, name='review_beneficiaries'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/manual-add/', views.manual_override_beneficiary, name='manual_override_beneficiary'),
    path('mswdo/schedule/<int:schedule_id>/edit/', views.edit_schedule, name='edit_schedule'),
    path('mswdo/schedule/<int:schedule_id>/cancel/', views.cancel_schedule, name='cancel_schedule'),
    path('mswdo/beneficiary/<int:entry_id>/details/', views.beneficiary_detail_modal, name='beneficiary_detail_modal'),
    
    # Manage Schedules Landing & AJAX
    path('mswdo/manage-schedules/', views.beneficiary_selection_landing, name='beneficiary_selection_landing'),
    path('mswdo/schedule/<int:schedule_id>/assign-staff/', views.assign_staff, name='assign_staff'),
    path('mswdo/search-staff/', views.search_staff, name='search_staff'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/search/', views.search_eligible_candidates, name='search_eligible_candidates'),
    
    path('mswdo/schedule/<int:schedule_id>/rfid/scan/', views.scan_rfid, name='scan_rfid'),
    path('mswdo/schedule/<int:schedule_id>/finish/', views.finish_distribution, name='finish_distribution'),
    path('mswdo/reports/generate-stub/', views.generate_report_stub, name='generate_report_stub'),

    # Walk-in Assistance
    path('staff/walkin/', views.staff_walkin, name='staff_walkin'),
    path('staff/walkin/rfid/', views.staff_walkin_rfid_lookup, name='staff_walkin_rfid'),
    path('staff/walkin/reactivate-family/', views.staff_walkin_reactivate_family, name='staff_walkin_reactivate_family'),
    path('staff/walkin/claim/', views.staff_walkin_claim, name='staff_walkin_claim'),
    path('staff/walkin/member/<int:member_id>/modal/', views.staff_walkin_member_modal, name='staff_walkin_member_modal'),
    path('staff/search-assistance/', views.search_assistance, name='search_assistance'),

    # Distribution Venue Management
    path('mswdo/venues/', views.venue_list, name='venue_list'),
    path('mswdo/venues/add/', views.venue_add, name='venue_add'),
    path('mswdo/venues/<int:venue_id>/edit/', views.venue_edit, name='venue_edit'),
    path('mswdo/venues/<int:venue_id>/deactivate/', views.venue_deactivate, name='venue_deactivate'),
    path('mswdo/venues/<int:venue_id>/activate/', views.venue_activate, name='venue_activate'),

    # Offline Sync Features
    path('schedule/<int:schedule_id>/download-backup/', views.download_beneficiary_backup, name='download_beneficiary_backup'),
    path('mswdo/schedule/<int:schedule_id>/skip-backup/', views.skip_beneficiary_backup, name='skip_beneficiary_backup'),
    path('prepare-offline-kit/', views.prepare_offline_kit, name='prepare_offline_kit'),
    path('import/beneficiary-list/', views.import_beneficiary_list_view, name='import_beneficiary_list'),
    path('import/full-sync/', views.import_full_sync_view, name='import_full_sync'),
    path('export/offline-claims/', views.export_offline_claims_view, name='export_offline_claims'),
    path('export/offline-claims/<int:schedule_id>/', views.export_offline_claims_view, name='export_offline_claims_schedule'),
    path('reconcile/claims-import/', views.reconcile_claims_import, name='reconcile_claims_import'),
    
    # Staff assigned schedules
    path('staff/assigned-schedules/', views.staff_assigned_schedules, name='staff_assigned_schedules'),
]
