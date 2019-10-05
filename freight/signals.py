from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Pricing
from .tasks import update_contracts_pricing


@receiver(post_save, sender=Pricing)
def pricing_save_handler(sender, instance, *args, **kwargs):
    """contract pricing needs to be updated after very pricing change"""
    update_contracts_pricing.delay()