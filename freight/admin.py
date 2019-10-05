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
    list_display = ('name', 'start_location', 'end_location', 'active')    
    list_filter = ('active',)
    

@admin.register(ContractHandler)
class ContractHandlerAdmin(admin.ModelAdmin):
    list_display = ('alliance', 'character', 'last_sync')
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

    # This will help you to disbale add functionality
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [        
        'contract_id',
        'status',
        'date_issued',
        'issuer',        
    ]
    list_filter = ('status',)
    search_fields = ['issuer']

    # This will help you to disbale add functionality
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False