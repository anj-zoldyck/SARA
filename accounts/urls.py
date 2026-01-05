from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.landing_page, name='landing'),

    path('mswdo/dashboard/', views.mswdo_dashboard, name='mswdo_dashboard'),
    path('mswdo/barangay/create/', views.create_barangay, name='create_barangay'),
    path('mswdo/barangay/deactivate/<int:user_id>/', views.deactivate_barangay, name='deactivate_barangay'),
    path('dashboard/', views.barangay_dashboard, name='barangay_dashboard'),

    path('zone/<int:zone_id>/', views.zone_detail, name='zone_detail'),
    path('zone/<int:zone_id>/add-household/', views.add_household, name='add_household'),

    path('household/<int:household_id>/', views.household_detail, name='household_detail'),
    path('household/<int:household_id>/add-family/', views.add_family, name='add_family'),

    path('family/<int:family_id>/', views.family_detail, name='family_detail'),
    path('family/<int:family_id>/add-member/', views.add_family_member, name='add_family_member'),

    path('member/<int:member_id>/edit/', views.edit_family_member, name='edit_family_member'),

]
