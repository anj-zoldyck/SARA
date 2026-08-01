from django.urls import path, reverse
from django.http import HttpResponseRedirect
from . import views

def family_members_redirect(request, family_id):
    return HttpResponseRedirect(reverse('family_detail', kwargs={'family_id': family_id}))

urlpatterns = [
    path('mswdo/barangays/', views.barangay_list, name='barangay_list'),
    path('mswdo/barangays/<int:barangay_id>/zones/', views.barangay_zones, name='barangay_zones'),
    path('mswdo/zones/<int:zone_id>/households/', views.zone_households, name='zone_households'),
    path('mswdo/households/<int:household_id>/', views.household_info, name='household_info'),
    path('mswdo/families/<int:family_id>/members/', family_members_redirect, name='family_members'),
    path('barangay/zones/<int:zone_id>/', views.zone_detail, name='zone_detail'),
    path('barangay/zones/<int:zone_id>/flood-prone-areas/', views.manage_flood_prone_areas, name='manage_flood_prone_areas'),
    path('barangay/zones/<int:zone_id>/flood-prone-areas/api/', views.manage_flood_prone_areas_api, name='manage_flood_prone_areas_api'),
    path('barangay/zones/<int:zone_id>/households/add/', views.add_household, name='add_household'),
    path('barangay/households/<int:household_id>/', views.household_detail, name='household_detail'),
    path('barangay/households/<int:household_id>/edit/', views.edit_household, name='edit_household'),
    path('barangay/households/<int:household_id>/families/add/', views.add_family, name='add_family'),
    path('barangay/families/<int:family_id>/', views.family_detail, name='family_detail'),
    path('barangay/families/<int:family_id>/members/add/', views.add_family_member, name='add_family_member'),
    path('barangay/members/<int:member_id>/edit/', views.edit_family_member, name='edit_family_member'),
    path('barangay/members/<int:member_id>/delete/', views.delete_family_member, name='delete_family_member'),
    path('barangay/members/<int:member_id>/details/', views.member_details_modal, name='member_details_modal'),
    path('barangay/households/<int:household_id>/modal/', views.household_modal_content, name='household_modal_content'),
    path('map/', views.household_map, name='household_map'),
    path('map/data/', views.household_map_data, name='household_map_data'),
    path('vulnerability-map/', views.household_vulnerability_map, name='household_vulnerability_map'),
    path('vulnerability-map/data/', views.household_vulnerability_data, name='household_vulnerability_data'),
    path('barangay/families/<int:family_id>/edit-name/', views.edit_family_name, name='edit_family_name'),
    path('barangay/households/<int:household_id>/delete/', views.delete_household, name='delete_household'),
    path('barangay/families/<int:family_id>/delete/', views.delete_family, name='delete_family'),
    # Import/Export
    path('barangay/zones/<int:zone_id>/import/upload/', views.import_members_upload, name='import_members_upload'),
    path('barangay/import/preview/', views.import_members_preview, name='import_members_preview'),
    path('barangay/import/commit/', views.import_members_commit, name='import_members_commit'),
    path('barangay/import/summary/', views.import_members_summary, name='import_members_summary'),
    path('barangay/households/<int:household_id>/export/', views.export_household_excel, name='export_household_excel'),
    path('barangay/families/<int:family_id>/export/', views.export_family_excel, name='export_family_excel'),
    path('mswdo/households/<int:household_id>/export/', views.export_household_excel, name='export_household_excel_mswdo'),
    path('mswdo/families/<int:family_id>/export/', views.export_family_excel, name='export_family_excel_mswdo'),
    path('mswdo/zones/<int:zone_id>/export/', views.export_zone_households_excel, name='export_zone_households_excel'),
    path('barangay/zones/<int:zone_id>/export/', views.export_zone_households_excel, name='export_zone_households_excel_barangay'),
]
