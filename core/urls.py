from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('barangay/dashboard/', views.barangay_dashboard, name='barangay_dashboard'),
    path('mswdo/audit-log/', views.audit_log_view, name='audit_log'),
    path('mswdo/api/demographics/<str:category>/', views.api_demographics, name='api_demographics'),
    path('mswdo/api/monthly-claims/<str:month>/', views.api_monthly_claims, name='api_monthly_claims'),
    path('mswdo/api/analytics-chart-data/', views.api_analytics_chart_data, name='api_analytics_chart_data'),
]
