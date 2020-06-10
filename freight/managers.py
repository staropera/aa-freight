from datetime import datetime
import json
import logging
from time import sleep

from bravado.exception import HTTPUnauthorized, HTTPForbidden

from django.db import models, transaction

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound

from esi.models import Token

from .app_settings import (
    FREIGHT_DISCORD_WEBHOOK_URL,
    FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL,
)
from .helpers.esi_fetch import esi_fetch
from .utils import LoggerAddTag, make_logger_prefix


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class PricingManager(models.Manager):
    def get_default(self):
        """return the default pricing if defined
        else the first pricing, which can be None if no pricing exists
        """
        pricing_qs = self.filter(is_active=True)
        pricing = pricing_qs.filter(is_default=True).first()
        if not pricing:
            pricing = pricing_qs.first()

        return pricing

    def get_or_default(self, pk: int = None):
        """returns the pricing for given pk if found else default pricing"""
        if pk:
            try:
                pricing = self.filter(is_active=True).get(pk=pk)
            except self.model.DoesNotExist:
                pricing = self.get_default()
        else:
            pricing = self.get_default()
        return pricing


class LocationManager(models.Manager):
    STATION_ID_START = 60000000
    STATION_ID_END = 69999999

    def get_or_create_from_esi(
        self, token: Token, location_id: int, add_unknown: bool = True
    ) -> tuple:
        """gets or creates location object with data fetched from ESI"""
        from .models import Location

        try:
            location = self.get(id=location_id)
            created = False
        except Location.DoesNotExist:
            location, created = self.update_or_create_from_esi(
                token=token, location_id=location_id, add_unknown=add_unknown
            )

        return location, created

    def update_or_create_from_esi(
        self, token: Token, location_id: int, add_unknown: bool = True
    ) -> tuple:
        """updates or creates location object with data fetched from ESI"""
        from .models import Location

        add_prefix = make_logger_prefix(location_id)

        if location_id >= self.STATION_ID_START and location_id <= self.STATION_ID_END:
            logger.info(add_prefix("Fetching station from ESI"))
            try:
                station = esi_fetch(
                    "Universe.get_universe_stations_station_id",
                    args={"station_id": location_id},
                    logger_tag=add_prefix(),
                )
                location, created = self.update_or_create(
                    id=location_id,
                    defaults={
                        "name": station["name"],
                        "solar_system_id": station["system_id"],
                        "type_id": station["type_id"],
                        "category_id": Location.CATEGORY_STATION_ID,
                    },
                )
            except Exception as ex:
                logger.exception(add_prefix("Failed to load station: {}".format(ex)))
                raise ex

        else:
            try:
                structure = esi_fetch(
                    "Universe.get_universe_structures_structure_id",
                    args={"structure_id": location_id},
                    token=token,
                    logger_tag=add_prefix(),
                )
                location, created = self.update_or_create(
                    id=location_id,
                    defaults={
                        "name": structure["name"],
                        "solar_system_id": structure["solar_system_id"],
                        "type_id": structure["type_id"],
                        "category_id": Location.CATEGORY_STRUCTURE_ID,
                    },
                )
            except (HTTPUnauthorized, HTTPForbidden) as ex:
                logger.warn(add_prefix("No access to this structure: {}".format(ex)))
                if add_unknown:
                    location, created = self.get_or_create(
                        id=location_id,
                        defaults={
                            "name": "Unknown structure {}".format(location_id),
                            "category_id": Location.CATEGORY_STRUCTURE_ID,
                        },
                    )
                else:
                    raise ex
            except Exception as ex:
                logger.exception(add_prefix("Failed to load structure: {}".format(ex)))
                raise ex

        return location, created


class EveEntityManager(models.Manager):
    def get_or_create_from_esi(self, id: int) -> tuple:
        """gets or creates entity object with data fetched from ESI"""
        from .models import EveEntity

        try:
            entity = self.get(id=id)
            created = False
        except EveEntity.DoesNotExist:
            entity, created = self.update_or_create_from_esi(id)

        return entity, created

    def update_or_create_from_esi(self, id: int) -> tuple:
        """updates or creates entity object with data fetched from ESI"""

        add_prefix = make_logger_prefix(id)

        try:
            response = esi_fetch(
                esi_path="Universe.post_universe_names",
                args={"ids": [id]},
                logger_tag=add_prefix(),
            )
            if len(response) != 1:
                raise ObjectNotFound(id, "unknown_type")
            else:
                entity_data = response[0]
            entity, created = self.update_or_create(
                id=entity_data["id"],
                defaults={
                    "name": entity_data["name"],
                    "category": entity_data["category"],
                },
            )
        except Exception as ex:
            logger.exception(
                add_prefix(
                    "Failed to load entity with id {} from ESI: {}".format(id, ex)
                )
            )
            raise ex

        return entity, created

    def update_or_create_from_evecharacter(
        self, character: EveCharacter, category: str
    ) -> tuple:
        """updates or creates EveEntity object from an EveCharacter object"""
        from .models import EveEntity

        add_prefix = make_logger_prefix(character.character_id)

        try:
            if category == EveEntity.CATEGORY_ALLIANCE:
                if not character.alliance_id:
                    raise ValueError("character is not an alliance member")
                eve_entity, created = self.update_or_create(
                    id=character.alliance_id,
                    defaults={
                        "name": character.alliance_name,
                        "category": EveEntity.CATEGORY_ALLIANCE,
                    },
                )
            elif category == EveEntity.CATEGORY_CORPORATION:
                eve_entity, created = self.update_or_create(
                    id=character.corporation_id,
                    defaults={
                        "name": character.corporation_name,
                        "category": EveEntity.CATEGORY_CORPORATION,
                    },
                )
            elif category == EveEntity.CATEGORY_CHARACTER:
                eve_entity, created = self.update_or_create(
                    id=character.character_id,
                    defaults={
                        "name": character.character_name,
                        "category": EveEntity.CATEGORY_CHARACTER,
                    },
                )
            else:
                raise ValueError("Invalid category: {}".format(category))

        except Exception as ex:
            logger.exception(
                add_prefix("Failed to convert to EveEntity: {}".format(ex))
            )
            raise ex

        return eve_entity, created


class ContractManager(models.Manager):
    def update_or_create_from_dict(
        self, handler: object, contract: dict, token: Token
    ) -> tuple:
        """updates or creates a contract from given dict"""
        # validate types
        self._ensure_datetime_type_or_none(contract, "date_accepted")
        self._ensure_datetime_type_or_none(contract, "date_completed")
        self._ensure_datetime_type_or_none(contract, "date_expired")
        self._ensure_datetime_type_or_none(contract, "date_issued")

        acceptor, acceptor_corporation = self._identify_contract_acceptor(contract)
        issuer_corporation, issuer = self._identify_contract_issuer(contract)
        date_accepted = (
            contract["date_accepted"] if "date_accepted" in contract else None
        )
        date_completed = (
            contract["date_completed"] if "date_completed" in contract else None
        )
        title = contract["title"] if "title" in contract else None
        start_location, end_location = self._identify_locations(contract, token)
        obj, created = self.update_or_create(
            handler=handler,
            contract_id=contract["contract_id"],
            defaults={
                "acceptor": acceptor,
                "acceptor_corporation": acceptor_corporation,
                "collateral": contract["collateral"],
                "date_accepted": date_accepted,
                "date_completed": date_completed,
                "date_expired": contract["date_expired"],
                "date_issued": contract["date_issued"],
                "days_to_complete": contract["days_to_complete"],
                "end_location": end_location,
                "for_corporation": contract["for_corporation"],
                "issuer_corporation": issuer_corporation,
                "issuer": issuer,
                "reward": contract["reward"],
                "start_location": start_location,
                "status": contract["status"],
                "title": title,
                "volume": contract["volume"],
                "pricing": None,
                "issues": None,
            },
        )
        return obj, created

    @staticmethod
    def _ensure_datetime_type_or_none(contract: dict, property_name: str):
        if contract[property_name] and not isinstance(
            contract[property_name], datetime
        ):
            raise TypeError("%s must be of type datetime" % property_name)

    def _identify_locations(self, contract: dict, token: Token) -> tuple:
        from .models import Location

        start_location, _ = Location.objects.get_or_create_from_esi(
            token, contract["start_location_id"]
        )
        end_location, _ = Location.objects.get_or_create_from_esi(
            token, contract["end_location_id"]
        )
        return start_location, end_location

    def _identify_contract_acceptor(self, contract: dict) -> tuple:
        from .models import EveEntity

        add_prefix = make_logger_prefix(contract["contract_id"])
        if int(contract["acceptor_id"]) != 0:
            try:
                entity, _ = EveEntity.objects.get_or_create_from_esi(
                    contract["acceptor_id"]
                )
                if entity.is_character:
                    try:
                        acceptor = EveCharacter.objects.get(character_id=entity.id)
                    except EveCharacter.DoesNotExist:
                        acceptor = EveCharacter.objects.create_character(
                            character_id=entity.id
                        )
                    try:
                        acceptor_corporation = EveCorporationInfo.objects.get(
                            corporation_id=acceptor.corporation_id
                        )
                    except EveCorporationInfo.DoesNotExist:
                        acceptor_corporation = EveCorporationInfo.objects.create_corporation(
                            corp_id=acceptor.corporation_id
                        )
                elif entity.is_corporation:
                    acceptor = None
                    try:
                        acceptor_corporation = EveCorporationInfo.objects.get(
                            corporation_id=entity.id
                        )
                    except EveCorporationInfo.DoesNotExist:
                        acceptor_corporation = EveCorporationInfo.objects.create_corporation(
                            corp_id=entity.id
                        )
                else:
                    raise ValueError(
                        "Acceptor has invalid category: {}".format(entity.category)
                    )

            except Exception as ex:
                logger.exception(
                    add_prefix(
                        "Failed to identify acceptor for this contract: {}".format(ex)
                    )
                )
                acceptor = None
                acceptor_corporation = None

        else:
            acceptor = None
            acceptor_corporation = None

        return acceptor, acceptor_corporation

    def _identify_contract_issuer(self, contract) -> tuple:
        try:
            issuer = EveCharacter.objects.get(character_id=contract["issuer_id"])
        except EveCharacter.DoesNotExist:
            issuer = EveCharacter.objects.create_character(
                character_id=contract["issuer_id"]
            )

        try:
            issuer_corporation = EveCorporationInfo.objects.get(
                corporation_id=contract["issuer_corporation_id"]
            )
        except EveCorporationInfo.DoesNotExist:
            issuer_corporation = EveCorporationInfo.objects.create_corporation(
                corp_id=contract["issuer_corporation_id"]
            )
        return issuer_corporation, issuer

    def update_pricing(self) -> None:
        """Updates contracts with matching pricing"""
        from .models import Pricing

        def _make_key(location_id_1: int, location_id_2: int) -> str:
            return "{}x{}".format(int(location_id_1), int(location_id_2))

        pricings = dict()
        for x in Pricing.objects.filter(is_active=True).order_by("-id"):
            pricings[_make_key(x.start_location_id, x.end_location_id)] = x
            if x.is_bidirectional:
                pricings[_make_key(x.end_location_id, x.start_location_id)] = x

        for contract in self.all():
            if contract.status == self.model.STATUS_OUTSTANDING or not contract.pricing:
                with transaction.atomic():
                    route_key = _make_key(
                        contract.start_location_id, contract.end_location_id
                    )
                    if route_key in pricings:
                        pricing = pricings[route_key]
                        issues_list = contract.get_price_check_issues(pricing)
                        if issues_list:
                            issues = json.dumps(issues_list)
                        else:
                            issues = None
                    else:
                        pricing = None
                        issues = None

                    contract.pricing = pricing
                    contract.issues = issues
                    contract.save()

    def send_notifications(self, force_sent=False, rate_limted=True) -> None:
        """Send notifications for outstanding contracts that have pricing"""
        add_tag = make_logger_prefix("send_notifications")
        logger.debug(add_tag("start"))

        # pilot notifications
        if FREIGHT_DISCORD_WEBHOOK_URL:
            contracts_qs = self.filter(
                status__exact=self.model.STATUS_OUTSTANDING
            ).exclude(pricing__exact=None)

            if not force_sent:
                contracts_qs = contracts_qs.filter(date_notified__exact=None)

            contracts_qs = contracts_qs.select_related()

            if contracts_qs.count() > 0:
                self._sent_pilot_notifications(contracts_qs, rate_limted, add_tag)
        else:
            logger.debug(add_tag("FREIGHT_DISCORD_WEBHOOK_URL not configured"))

        # customer notifications
        if FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL:
            contracts_qs = self.filter(
                status__in=self.model.STATUS_FOR_CUSTOMER_NOTIFICATION
            ).exclude(pricing__exact=None)

            contracts_qs = contracts_qs.select_related()

            if contracts_qs.count() > 0:
                self._sent_customer_notifications(
                    contracts_qs, rate_limted, force_sent, add_tag
                )

        else:
            logger.debug(
                add_tag("FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL not configured")
            )

    def _sent_pilot_notifications(self, contracts_qs, rate_limted, add_tag) -> None:
        logger.info(
            add_tag(
                "Trying to send pilot notifications for"
                + " {} contracts".format(contracts_qs.count())
            )
        )

        for contract in contracts_qs:
            if not contract.has_expired:
                contract.send_pilot_notification()
                if rate_limted:
                    sleep(1)
            else:
                logger.debug(
                    add_tag("contract {} has expired".format(contract.contract_id))
                )

    def _sent_customer_notifications(
        self, contracts_qs, rate_limted, force_sent, add_tag
    ) -> None:
        logger.debug(
            "%s: Checking %d contracts if customer " "notifications need to be sent",
            add_tag(),
            contracts_qs.count(),
        )
        for contract in contracts_qs:
            if contract.has_expired:
                logger.debug(
                    "%s: contract %d has expired", add_tag(), contract.contract_id
                )
            elif contract.has_stale_status:
                logger.debug(
                    "%s: contract %d has stale status", add_tag(), contract.contract_id
                )
            else:
                contract.send_customer_notification(force_sent)
                if rate_limted:
                    sleep(1)
