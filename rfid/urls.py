from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/rfid/overview/', views.rfid_overview, name='rfid_overview'),
    path('mswdo/rfid/register/', views.register_rfid, name='register_rfid'),
    path('mswdo/rfid/register/<int:family_id>/', views.register_rfid, name='register_rfid_family'),
    path('mswdo/families/<int:family_id>/deactivate-rfid/', views.deactivate_rfid, name='deactivate_rfid'),
]
