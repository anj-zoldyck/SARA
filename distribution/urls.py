from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/schedule-distribution/', views.schedule_distribution, name='schedule_distribution'),
    path('mswdo/schedule/<int:schedule_id>/generate/', views.generate_beneficiaries, name='generate_beneficiaries'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/', views.review_beneficiaries, name='review_beneficiaries'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/manual-add/', views.manual_override_beneficiary, name='manual_override_beneficiary'),
    path('mswdo/beneficiary/<int:entry_id>/details/', views.beneficiary_detail_modal, name='beneficiary_detail_modal'),
    
    # Beneficiary Selection Landing & AJAX
    path('mswdo/beneficiary-selection/', views.beneficiary_selection_landing, name='beneficiary_selection_landing'),
    path('mswdo/schedule/<int:schedule_id>/beneficiaries/search/', views.search_eligible_candidates, name='search_eligible_candidates'),
    
    path('mswdo/rfid/scan/', views.scan_rfid, name='scan_rfid'),
    path('mswdo/schedule/<int:schedule_id>/finish/', views.finish_distribution, name='finish_distribution'),
    path('mswdo/reports/generate-stub/', views.generate_report_stub, name='generate_report_stub'),

    # Walk-in Assistance
    path('staff/walkin/', views.staff_walkin, name='staff_walkin'),
    path('staff/walkin/rfid/', views.staff_walkin_rfid_lookup, name='staff_walkin_rfid'),
    path('staff/walkin/claim/', views.staff_walkin_claim, name='staff_walkin_claim'),
    path('staff/walkin/member/<int:member_id>/modal/', views.staff_walkin_member_modal, name='staff_walkin_member_modal'),
]
