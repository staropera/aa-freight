from django.contrib import admin

from . import tasks
from .app_settings import FREIGHT_DEVELOPER_MODE
from .models import (
    ContractHandler,
    Contract,
    ContractCustomerNotification,
    EveEntity,
    Location,
    Pricing,
)
from .tasks import update_locations


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "_category", "_solar_system")
    list_filter = ("category_id",)
    search_fields = ["name"]
    list_select_related = True

    actions = ["update_location"]

    if not FREIGHT_DEVELOPER_MODE:
        list_display_links = None

    def _category(self, obj):
        return obj.get_category_id_display()

    _category.admin_order_field = "category_id"

    def _solar_system(self, obj):
        return obj.solar_system_name

    def has_add_permission(self, request):
        if FREIGHT_DEVELOPER_MODE:
            return True
        else:
            return False

    def has_change_permission(self, request):
        if FREIGHT_DEVELOPER_MODE:
            return True
        else:
            return False

    def update_location(self, request, queryset):
        location_ids = list()
        for obj in queryset:
            location_ids.append(obj.pk)

        update_locations.delay(location_ids)
        self.message_user(
            request,
            "Started updating {} locations. "
            "This can take a short while to complete.".format(len(location_ids)),
        )

    update_location.short_description = "Update selected locations from ESI"


if FREIGHT_DEVELOPER_MODE:

    @admin.register(EveEntity)
    class EveEntityAdmin(admin.ModelAdmin):
        list_display = ("name", "category")
        list_filter = ("category",)


@admin.register(Pricing)
class PricingAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "start_location",
        "end_location",
        "_bidirectional",
        "_default",
        "_active",
    )
    list_filter = (
        "is_bidirectional",
        "is_active",
        ("start_location", admin.RelatedOnlyFieldListFilter),
        ("end_location", admin.RelatedOnlyFieldListFilter),
    )
    list_select_related = True

    def _bidirectional(self, obj):
        return obj.is_bidirectional

    _bidirectional.boolean = True

    def _active(self, obj):
        return obj.is_active

    _active.boolean = True

    def _default(self, obj):
        return obj.is_default

    _default.boolean = True


@admin.register(ContractHandler)
class ContractHandlerAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "character",
        "operation_mode",
        "last_sync",
        "_is_sync_ok",
    )
    actions = ("start_sync", "send_notifications", "update_pricing")

    if not FREIGHT_DEVELOPER_MODE:
        readonly_fields = (
            "organization",
            "character",
            "operation_mode",
            "version_hash",
            "last_sync",
            "last_error",
        )

    def _is_sync_ok(self, obj):
        return obj.is_sync_ok

    _is_sync_ok.boolean = True
    _is_sync_ok.short_description = "sync ok"

    def start_sync(self, request, queryset):

        for obj in queryset:
            tasks.run_contracts_sync.delay(force_sync=True, user_pk=request.user.pk)
            text = "Started syncing contracts for: {} ".format(obj)
            text += "You will receive a report once it is completed."

            self.message_user(request, text)

    start_sync.short_description = "Fetch contracts from Eve Online server"

    def send_notifications(self, request, queryset):

        for obj in queryset:
            tasks.send_contract_notifications.delay(force_sent=True)
            text = "Started sending notifications for: {} ".format(obj)

            self.message_user(request, text)

    send_notifications.short_description = (
        "Send notifications for outstanding contracts"
    )

    def update_pricing(self, request, queryset):
        del queryset
        tasks.update_contracts_pricing.delay()
        self.message_user(
            request, "Started updating pricing relations for all contracts"
        )

    update_pricing.short_description = "Update pricing info for all contracts"

    def has_add_permission(self, request):
        return False


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [
        "contract_id",
        "status",
        "date_issued",
        "issuer",
        "_pilots_notified",
        "_customer_notified",
    ]
    list_filter = (
        "status",
        ("issuer", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ["issuer"]

    list_select_related = True

    actions = ["send_pilots_notification", "send_customer_notification"]

    def _pilots_notified(self, contract):
        return contract.date_notified is not None

    _pilots_notified.boolean = True

    def _customer_notified(self, contract):
        return ", ".join(
            sorted(
                [x.status for x in contract.contractcustomernotification_set.all()],
                reverse=True,
            )
        )

    def send_pilots_notification(self, request, queryset):
        for obj in queryset:
            obj.send_pilot_notification()
            self.message_user(
                request,
                "Sent pilots notification for contract {} to Discord".format(
                    obj.contract_id
                ),
            )

    send_pilots_notification.short_description = (
        "Sent pilots notification for selected contracts to Discord"
    )

    def send_customer_notification(self, request, queryset):
        for obj in queryset:
            obj.send_customer_notification(force_sent=True)
            self.message_user(
                request,
                "Sent customer notification for contract {} to Discord".format(
                    obj.contract_id
                ),
            )

    send_customer_notification.short_description = (
        "Sent customer notification for selected contracts to Discord"
    )

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
