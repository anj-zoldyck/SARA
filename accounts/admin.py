from django.contrib import admin
from .models import User, Family, AidClaim, Program, AidCategory, Assistance

admin.site.register(User)
admin.site.register(Family)
admin.site.register(AidClaim)

class AidCategoryInline(admin.TabularInline):
    model = AidCategory
    extra = 1

class AssistanceInline(admin.TabularInline):
    model = Assistance
    extra = 1

@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    inlines = [AidCategoryInline]

@admin.register(AidCategory)
class AidCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'program', 'is_active']
    list_filter = ['program']

@admin.register(Assistance)
class AssistanceAdmin(admin.ModelAdmin):
    list_display = ['program', 'aid_category', 'beneficiary_type', 'minimum_age', 'is_active']
    list_filter = ['program', 'beneficiary_type']
