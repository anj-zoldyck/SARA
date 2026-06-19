from django.urls import path
from . import views

urlpatterns = [
    path('mswdo/programs/', views.program_list, name='program_list'),
    path('mswdo/programs/add/', views.add_program, name='add_program'),
    path('mswdo/programs/<int:program_id>/edit/', views.edit_program, name='edit_program'),
    path('mswdo/programs/<int:program_id>/toggle/', views.toggle_program, name='toggle_program'),
    path('mswdo/programs/<int:program_id>/aid-categories/add/', views.add_aid_category, name='add_aid_category'),
    path('mswdo/programs/assistance/add/', views.add_assistance, name='add_assistance'),
    path('mswdo/programs/assistance/<int:assistance_id>/toggle/', views.toggle_assistance, name='toggle_assistance'),
    path('mswdo/programs/assistance/<int:assistance_id>/edit/', views.edit_assistance, name='edit_assistance'),
]
