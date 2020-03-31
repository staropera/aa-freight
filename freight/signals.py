from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Pricing
from .tasks import update_contracts_pricing


@receiver(post_save, sender=Pricing, dispatch_uid="id_update_contracts_pricing")
def pricing_save_handler(sender, instance, *args, **kwargs):
    """contract pricing needs to be updated after every pricing change"""
    update_contracts_pricing.delay()
