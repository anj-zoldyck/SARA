from django.contrib import admin
from .models import Zone, Household, Family, FamilyMember

admin.site.register(Zone)
admin.site.register(Household)
admin.site.register(Family)
admin.site.register(FamilyMember)
