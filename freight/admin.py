from django import forms
from django.contrib import admin
from django.utils.html import format_html

from . import tasks
from .app_settings import FREIGHT_DEVELOPER_MODE
from .models import *


if FREIGHT_DEVELOPER_MODE:
    @admin.register(Location)
    class LocationAdmin(admin.ModelAdmin):
        list_display = ('id', 'name', 'category_id')    
        list_filter = ('category_id',)
        search_fields = ['name']
        list_select_related = True


    @admin.register(EveEntity)
    class EveEntityAdmin(admin.ModelAdmin):
        list_display = ('name', 'category')
        list_filter = ('category', )


@admin.register(Pricing)
class PricingAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_location', 'end_location', 'active')
    list_filter = (
        'active',
        ('start_location', admin.RelatedOnlyFieldListFilter),
        ('end_location', admin.RelatedOnlyFieldListFilter),
    )
    list_select_related = True

@admin.register(ContractHandler)
class ContractHandlerAdmin(admin.ModelAdmin):
    list_display = ('organization', 'character', 'operation_mode', 'last_sync')
    actions = ('send_notifications', 'start_sync', 'update_pricing')

    if not FREIGHT_DEVELOPER_MODE:            
        readonly_fields=(
            'organization', 
            'character', 
            'operation_mode', 
            'version_hash', 
            'last_sync', 
            'last_error', 
        )


    def start_sync(self, request, queryset):
                        
        for obj in queryset:            
            tasks.run_contracts_sync.delay(                
                force_sync=True,
                user_pk=request.user.pk
            )            
            text = 'Started syncing contracts for: {} '.format(obj)
            text += 'You will receive a report once it is completed.'

            self.message_user(
                request, 
                text
            )
    
    start_sync.short_description = "Fetch contracts from Eve Online server"

    def send_notifications(self, request, queryset):
                        
        for obj in queryset:            
            tasks.send_contract_notifications.delay(                
                force_sent=True
            )            
            text = 'Started sending notifications for: {} '.format(obj)
            
            self.message_user(
                request, 
                text
            )
    
    send_notifications.short_description = \
        "Send notifications for outstanding contracts"

    def update_pricing(self, request, queryset):
                        
        for obj in queryset:            
            tasks.update_contracts_pricing.delay()            
            self.message_user(
                request, 
                'Started updating pricing releation for all contracts'
            )
    
    update_pricing.short_description = "Update pricing info for all contracts"
    
    def has_add_permission(self, request):
        return False

    

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [        
        'contract_id',
        'status',
        'date_issued',
        'issuer',
        'pilots_notified',
        'customer_notified'
    ]
    list_filter = (
        'status',
        ('issuer', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ['issuer']

    list_select_related = True

    def pilots_notified(self, contract):
        return contract.date_notified is not None

    pilots_notified.boolean = True

    def customer_notified(self, contract):
        return ', '.join(sorted([
                x.status 
                for x in contract.contractcustomernotification_set\
                    .all()
            ], reverse=True
        ))

    actions = ['send_pilots_notification', 'send_customer_notification']

    def send_pilots_notification(self, request, queryset):
                        
        for obj in queryset:            
            obj.send_pilot_notification()
            self.message_user(
                request, 
                'Sent pilots notification for contract {} to Discord'.format(
                    obj.contract_id
                )
            )
    
    send_pilots_notification.short_description = \
        "Sent pilots notification for selected contracts to Discord"

    def send_customer_notification(self, request, queryset):
                        
        for obj in queryset:            
            obj.send_customer_notification(force_sent=True)
            self.message_user(
                request, 
                'Sent customer notification for contract {} to Discord'.format(
                    obj.contract_id
                )
            )
    
    send_customer_notification.short_description = \
        "Sent customer notification for selected contracts to Discord"

    # This will help you to disbale add functionality
    def has_add_permission(self, request):
        if FREIGHT_DEVELOPER_MODE:
            return True
        else:
            return False

    def has_change_permission(self, request, obj=None):
        if FREIGHT_DEVELOPER_MODE:
            return True
        else:
            return False


if FREIGHT_DEVELOPER_MODE:
    @admin.register(ContractCustomerNotification)
    class ContractCustomerNotificationAdmin(admin.ModelAdmin):
        pass