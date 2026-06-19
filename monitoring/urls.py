from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/rfid/monitoring/', views.rfid_claim_monitoring, name='rfid_claim_monitoring'),
    path('mswdo/rfid/live-claims/', views.rfid_live_claims, name='rfid_live_claims'),
    path('mswdo/schedule/status/', views.schedule_status, name='schedule_status'),
    path('mswdo/aid/', views.aid_type_list, name='aid_type_list'),
    path('mswdo/aid/<int:assistance_id>/barangays/', views.aid_barangay_list, name='aid_barangay_list'),
    path('mswdo/aid/<int:assistance_id>/barangays/<int:barangay_id>/', views.aid_barangay_detail, name='aid_barangay_detail'),
    path('mswdo/analytics/', views.analytics, name='analytics'),
    path('ajax/get-family-members/', views.get_family_members, name='get_family_members'),
    path('ajax/get-aid-categories/', views.get_aid_categories, name='get_aid_categories'),
    path('barangay/schedule-status/', views.barangay_schedule_status, name='barangay_schedule_status'),
    path('barangay/analytics/', views.barangay_analytics, name='barangay_analytics'),
    path('schedule-status/', views.schedule_status, name='schedule_status'),
]
