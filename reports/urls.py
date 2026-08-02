from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/reports/', views.aid_reports, name='aid_reports'),
    path('mswdo/reports/generate-summary/', views.generate_summary_report, name='generate_summary_report'),
    path('mswdo/reports/generate-list/', views.generate_beneficiary_list_report, name='generate_beneficiary_list_report'),
]
