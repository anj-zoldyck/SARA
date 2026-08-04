from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/rfid/overview/', views.rfid_overview, name='rfid_overview'),
    path('mswdo/rfid/register/', views.register_rfid, name='register_rfid'),
    path('mswdo/rfid/register/<int:family_id>/', views.register_rfid, name='register_rfid_family'),
    path('mswdo/families/<int:family_id>/deactivate-rfid/', views.deactivate_rfid, name='deactivate_rfid'),
    path('mswdo/rfid/barangay/<int:barangay_id>/', views.barangay_rfid_detail, name='barangay_rfid_detail'),
    path('mswdo/rfid/family/<int:family_id>/members/', views.family_members_modal, name='family_members_modal'),
]
