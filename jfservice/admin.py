from django.contrib import admin
from django.utils.html import format_html
from django import forms
from .models import *
from . import tasks


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category_id')    
    list_filter = ('category_id',)
    search_fields = ['name']


@admin.register(Pricing)
class PricingAdmin(admin.ModelAdmin):
    list_display = ('id', 'start_location', 'end_location', 'active')    
    list_filter = ('active',)
          

@admin.register(ContractsHandler)
class ContractsHandlerAdmin(admin.ModelAdmin):
    
    actions = ['start_sync']

    def start_sync(self, request, queryset):
                        
        for obj in queryset:            
            tasks.sync_contracts.delay(
                contracts_handler_pk=obj.pk, 
                force_sync=True,
                user_pk=request.user.pk
            )            
            text = 'Started syncing contracts for: {} '.format(obj)
            text += 'You will receive a report once it is completed.'

            self.message_user(
                request, 
                text
            )
    
    start_sync.short_description = "Sync contracts"


admin.site.register(Contract)

