from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/schedule/set/', views.set_aid_schedule, name='set_aid_schedule'),
    path('mswdo/rfid/scan/', views.scan_rfid, name='scan_rfid'),
    
]
