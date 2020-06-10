import logging

from celery import shared_task, chain

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from .models import ContractHandler, Contract, Location
from .utils import LoggerAddTag


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


def _get_user(user_pk) -> User:
    """returns the user or None. Logs if user is requested but can't be found."""
    user = None
    if user_pk:
        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            logger.warning("Ignoring non-existing user with pk {}".format(user_pk))
    return user


def _get_contract_handler() -> ContractHandler:
    handler = ContractHandler.objects.first()
    if not handler:
        logger.warning("contract handler was found")
        raise ObjectDoesNotExist()
    else:
        return handler


@shared_task
def update_contracts_esi(force_sync=False, user_pk=None) -> None:
    """start syncing contracts"""
    _get_contract_handler().update_contracts_esi(force_sync, user=_get_user(user_pk))


@shared_task
def send_contract_notifications(force_sent=False, rate_limted=True) -> None:
    """Send notification about outstanding contracts that have pricing"""
    try:
        Contract.objects.send_notifications(force_sent, rate_limted)

    except Exception as ex:
        logger.exception("An unexpected error ocurred: {}".format(ex))


@shared_task
def run_contracts_sync(force_sync=False, user_pk=None) -> None:
    """main task coordinating contract sync"""
    my_chain = chain(
        update_contracts_esi.si(force_sync, user_pk), send_contract_notifications.si()
    )
    my_chain.delay()


@shared_task
def update_contracts_pricing() -> None:
    """Updates pricing for all contracts"""
    logger.info("Started updating contracts pricing")
    try:
        Contract.objects.update_pricing()

    except Exception as ex:
        logger.exception("An unexpected error ocurred: {}".format(ex))


@shared_task
def update_location(location_id: int) -> None:
    """Updates the location from ESI """
    try:
        Location.objects.get(id=location_id)
    except Location.DoesNotExist:
        logger.warning(
            "Tried to update a non-existing location with ID {}".format(location_id)
        )
    else:
        token = _get_contract_handler().token()
        Location.objects.update_or_create_from_esi(location_id=location_id, token=token)


@shared_task
def update_locations(location_ids: list) -> None:
    """Updates the locations from ESI """

    for location_id in location_ids:
        update_location.delay(location_id)
