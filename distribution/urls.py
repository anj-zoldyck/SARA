from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/schedule/set/', views.set_aid_schedule, name='set_aid_schedule'),
    path('mswdo/rfid/scan/', views.scan_rfid, name='scan_rfid'),
    
    # Walk-in Assistance
    path('staff/walkin/', views.staff_walkin, name='staff_walkin'),
    path('staff/walkin/rfid/', views.staff_walkin_rfid_lookup, name='staff_walkin_rfid'),
    path('staff/walkin/claim/', views.staff_walkin_claim, name='staff_walkin_claim'),
    path('staff/walkin/member/<int:member_id>/modal/', views.staff_walkin_member_modal, name='staff_walkin_member_modal'),
]
