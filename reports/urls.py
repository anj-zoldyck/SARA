from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/reports/', views.aid_reports, name='aid_reports'),
]
