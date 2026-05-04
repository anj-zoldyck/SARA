from django.contrib import admin
from .models import User, Family, AidClaim

admin.site.register(User)
admin.site.register(Family)
admin.site.register(AidClaim)

#@admin.register(AidOfTheDay)
#class AidOfTheDayAdmin(admin.ModelAdmin):
#    list_display = ('date', 'aid_type')
#    ordering = ('-date',)
# Register your models here.
