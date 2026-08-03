from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('barangay/dashboard/', views.barangay_dashboard, name='barangay_dashboard'),
    path('mswdo/audit-log/', views.audit_log_view, name='audit_log'),
]
