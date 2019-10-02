from django.contrib import admin
from .models import *

@admin.register(JfService)
class JfServiceAdmin(admin.ModelAdmin):
    pass

admin.site.register(Contract)
admin.site.register(Structure)
