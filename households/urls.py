from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/barangays/', views.barangay_list, name='barangay_list'),
    path('mswdo/barangays/<int:barangay_id>/zones/', views.barangay_zones, name='barangay_zones'),
    path('mswdo/zones/<int:zone_id>/households/', views.zone_households, name='zone_households'),
    path('mswdo/households/<int:household_id>/', views.household_info, name='household_info'),
    path('mswdo/families/<int:family_id>/members/', views.family_members, name='family_members'),
    path('barangay/zones/<int:zone_id>/', views.zone_detail, name='zone_detail'),
    path('barangay/zones/<int:zone_id>/households/add/', views.add_household, name='add_household'),
    path('barangay/households/<int:household_id>/', views.household_detail, name='household_detail'),
    path('barangay/households/<int:household_id>/edit/', views.edit_household, name='edit_household'),
    path('barangay/households/<int:household_id>/families/add/', views.add_family, name='add_family'),
    path('barangay/families/<int:family_id>/', views.family_detail, name='family_detail'),
    path('barangay/families/<int:family_id>/members/add/', views.add_family_member, name='add_family_member'),
    path('barangay/members/<int:member_id>/edit/', views.edit_family_member, name='edit_family_member'),
    path('barangay/members/<int:member_id>/details/', views.member_details_modal, name='member_details_modal'),
    path('barangay/households/<int:household_id>/modal/', views.household_modal_content, name='household_modal_content'),
    path('map/', views.household_map, name='household_map'),
    path('map/data/', views.household_map_data, name='household_map_data'),
    path('vulnerability-map/', views.household_vulnerability_map, name='household_vulnerability_map'),
    path('vulnerability-map/data/', views.household_vulnerability_data, name='household_vulnerability_data'),
]
