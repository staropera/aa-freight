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
    actions = ['send_notifications', 'start_sync', 'update_pricing']

    def start_sync(self, request, queryset):
                        
        for obj in queryset:            
            tasks.sync_contracts.delay(
                handler_pk=obj.pk, 
                force_sync=True,
                user_pk=request.user.pk
            )            
            text = 'Started syncing contracts for: {} '.format(obj)
            text += 'You will receive a report once it is completed.'

            self.message_user(
                request, 
                text
            )
    
    start_sync.short_description = "Sync contracts with Eve Online server"

    def send_notifications(self, request, queryset):
                        
        for obj in queryset:            
            tasks.send_contract_notifications.delay(
                handler_pk=obj.pk, 
                force_sent=True
            )            
            text = 'Started sending notifications for: {} '.format(obj)
            
            self.message_user(
                request, 
                text
            )
    
    send_notifications.short_description = "Send notifications for outstanding contracts"

    def update_pricing(self, request, queryset):
                        
        for obj in queryset:            
            tasks.update_contracts_pricing_relations.delay()            
            self.message_user(
                request, 
                'Started updating pricing releation for all contracts'
            )
    
    update_pricing.short_description = "Update pricing info for all contracts"

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