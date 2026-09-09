from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/reports/', views.aid_reports, name='aid_reports'),
    path('mswdo/reports/walkin/', views.walkin_reports, name='walkin_reports'),
    path('mswdo/reports/distribution-claims/', views.distribution_claims, name='distribution_claims'),
    path('mswdo/reports/distribution/<int:schedule_id>/', views.distribution_report, name='distribution_report'),
    path('mswdo/reports/distribution/<int:schedule_id>/export/', views.export_distribution_report, name='export_distribution_report'),
    path('mswdo/reports/distribution-claims/import/', views.import_distribution_claims_view, name='import_distribution_claims'),
    path('mswdo/reports/generate-summary/', views.generate_summary_report, name='generate_summary_report'),
    path('mswdo/reports/generate-list/', views.generate_beneficiary_list_report, name='generate_beneficiary_list_report'),
    path('mswdo/reports/generate-walkin-summary/', views.generate_walkin_summary_report, name='generate_walkin_summary_report'),
    path('mswdo/reports/generate-walkin-list/', views.generate_walkin_beneficiary_list_report, name='generate_walkin_beneficiary_list_report'),
]
