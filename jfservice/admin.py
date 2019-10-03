from django.contrib import admin
from .models import *
from . import tasks

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


admin.site.register(Pricing)

admin.site.register(Contract)

admin.site.register(Location)

admin.site.register(Structure)
