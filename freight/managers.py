import logging
import json
from time import sleep

from bravado.exception import HTTPUnauthorized, HTTPForbidden

from django.db import models, transaction

from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.eveonline.providers import ObjectNotFound

from .app_settings import (
    FREIGHT_DISCORD_WEBHOOK_URL, FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL
)
from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class LocationManager(models.Manager):
    STATION_ID_START = 60000000
    STATION_ID_END = 69999999
    
    def get_or_create_from_esi(
        self, 
        esi_client: object, 
        location_id: int,
        add_unknown: bool = True
    ) -> list:
        """gets or creates location object with data fetched from ESI"""
        from .models import Location
        try:
            location = self.get(id=location_id)
            created = False
        except Location.DoesNotExist:
            location, created = self.update_or_create_from_esi(
                esi_client, 
                location_id,
                add_unknown
            )
        
        return location, created

    def update_or_create_from_esi(
        self, 
        esi_client: object, 
        location_id: int, 
        add_unknown: bool = True
    ) -> list:
        """updates or creates location object with data fetched from ESI"""
        from .models import Location

        addPrefix = make_logger_prefix(location_id)

        if (location_id >= self.STATION_ID_START 
                and location_id <= self.STATION_ID_END):
            logger.info(addPrefix('Fetching station from ESI'))
            try:
                station = esi_client.Universe\
                    .get_universe_stations_station_id(
                        station_id=location_id
                    ).result()
                location, created = self.update_or_create(
                    id=location_id,
                    defaults={
                        'name': station['name'],                    
                        'solar_system_id': station['system_id'],
                        'type_id': station['type_id'],                    
                        'category_id': Location.CATEGORY_STATION_ID
                    }
                ) 
            except Exception as ex:
                logger.exception(addPrefix(
                    'Failed to load station: {}'.format(ex)
                ))
                raise ex
            
        else:
            logger.info(addPrefix('Fetching structure from ESI'))
            try:
                structure = esi_client.Universe\
                    .get_universe_structures_structure_id(
                        structure_id=location_id
                    ).result()            
                location, created = self.update_or_create(
                    id=location_id,
                    defaults={
                        'name': structure['name'],                    
                        'solar_system_id': structure['solar_system_id'],
                        'type_id': structure['type_id'],
                        'category_id': Location.CATEGORY_STRUCTURE_ID
                    }
                )      
            except (HTTPUnauthorized, HTTPForbidden) as ex:
                logger.warn(addPrefix(
                    'No access to this structure: {}'.format(ex)
                ))      
                if add_unknown:
                    location, created = self.get_or_create(
                        id=location_id,
                        defaults={
                            'name': 'Unknown structure {}'.format(location_id),
                            'category_id': Location.CATEGORY_STRUCTURE_ID
                        }
                    )
                else:
                    raise ex
            except Exception as ex:
                logger.exception(addPrefix(
                    'Failed to load structure: {}'.format(ex)
                ))      
                raise ex
       
        return location, created


class EveEntityManager(models.Manager):
    
    def get_or_create_from_esi(
        self, id: int, esi_client: object = None
    ) -> list:
        """gets or creates entity object with data fetched from ESI"""
        from .models import EveEntity
        try:
            entity = self.get(id=id)
            created = False
        except EveEntity.DoesNotExist:
            entity, created = self.update_or_create_from_esi(id, esi_client)
        
        return entity, created

    def update_or_create_from_esi(
        self, id: int, esi_client: object = None
    ) -> list:
        """updates or creates entity object with data fetched from ESI"""
        
        addPrefix = make_logger_prefix(id)
        
        logger.info(addPrefix('Fetching entity from ESI'))
        try:
            if not esi_client:
                esi_client = esi_client_factory(
                    spec_file=get_swagger_spec_path()
                )
            response = esi_client.Universe.post_universe_names(
                ids=[id]
            ).result()
            if len(response) != 1:
                raise ObjectNotFound(id, 'unknown_type')
            else:
                entity_data = response[0]
            entity, created = self.update_or_create(
                id=entity_data['id'],
                defaults={
                    'name': entity_data['name'],
                    'category': entity_data['category'],
                }
            ) 
        except Exception as ex:
            logger.exception(addPrefix(
                'Failed to load entity with id {} from ESI: {}'.format(id, ex)
            ))
            raise ex
        
        return entity, created

    def update_or_create_from_evecharacter(
        self,             
        character: EveCharacter,
        category: str
    ) -> list:
        """updates or creates EveEntity object from an EveCharacter object"""
        from .models import EveEntity
        
        addPrefix = make_logger_prefix(character.character_id)

        try:            
            if category == EveEntity.CATEGORY_ALLIANCE:            
                if not character.alliance_id:
                    raise ValueError('character is not an alliance member')
                eve_entity, created = self.update_or_create(
                    id=character.alliance_id,
                    defaults={
                        'name': character.alliance_name,
                        'category': EveEntity.CATEGORY_ALLIANCE,
                    }
                )
            elif category == EveEntity.CATEGORY_CORPORATION:
                eve_entity, created = self.update_or_create(
                    id=character.corporation_id,
                    defaults={
                        'name': character.corporation_name,
                        'category': EveEntity.CATEGORY_CORPORATION,
                    }
                )
            elif category == EveEntity.CATEGORY_CHARACTER:
                eve_entity, created = self.update_or_create(
                    id=character.character_id,
                    defaults={
                        'name': character.character_name,
                        'category': EveEntity.CATEGORY_CHARACTER,
                    }
                )
            else:
                raise ValueError('Invalid category: {}'. format(category))
        
        except Exception as ex:
            logger.exception(addPrefix(
                'Failed to convert to EveEntity: {}'.format(ex)
            ))
            raise ex

        return eve_entity, created


class ContractManager(models.Manager):
    
    def update_or_create_from_dict(
        self, 
        handler: object, 
        contract: dict, 
        esi_client: object
    ):
        """updates or creates a contract from given dict"""
        from .models import Contract, Location, EveEntity
        
        addPrefix = make_logger_prefix(contract['contract_id'])

        if int(contract['acceptor_id']) != 0:
            try:
                entity, _ = EveEntity.objects.get_or_create_from_esi(
                    contract['acceptor_id'],
                    esi_client
                )
                if entity.is_character:
                    try:
                        acceptor = EveCharacter.objects.get(
                            character_id=entity.id
                        )
                    except EveCharacter.DoesNotExist:
                        acceptor = EveCharacter.objects.create_character(
                            character_id=entity.id
                        )
                    try:
                        acceptor_corporation = EveCorporationInfo.objects.get(
                            corporation_id=acceptor.corporation_id
                        )
                    except EveCorporationInfo.DoesNotExist:
                        acceptor_corporation = \
                            EveCorporationInfo.objects.create_corporation(
                                corp_id=acceptor.corporation_id
                            )
                elif entity.is_corporation:
                    acceptor = None
                    try:
                        acceptor_corporation = EveCorporationInfo.objects.get(
                            corporation_id=entity.id
                        )
                    except EveCorporationInfo.DoesNotExist:
                        acceptor_corporation = \
                            EveCorporationInfo.objects.create_corporation(
                                corp_id=entity.id
                            )
                else:
                    raise ValueError(
                        'Acceptor has invalid category: {}'.format(
                            entity.category
                        )
                    )

            except Exception as ex:
                logger.exception(addPrefix(
                    'Failed to identify acceptor for this contract: {}'.format(
                        ex
                    )
                ))
                acceptor = None
                acceptor_corporation = None

        else:
            acceptor = None
            acceptor_corporation = None

        try:
            issuer = EveCharacter.objects.get(
                character_id=contract['issuer_id']
            )
        except EveCharacter.DoesNotExist:
            issuer = EveCharacter.objects.create_character(
                character_id=contract['issuer_id']
            )

        try:
            issuer_corporation = EveCorporationInfo.objects.get(
                corporation_id=contract['issuer_corporation_id']
            )
        except EveCorporationInfo.DoesNotExist:
            issuer_corporation = EveCorporationInfo.objects.create_corporation(
                corp_id=contract['issuer_corporation_id']
            )
        
        date_accepted = contract['date_accepted'] \
            if 'date_accepted' in contract else None
        date_completed = contract['date_completed'] \
            if 'date_completed' in contract else None
        title = contract['title'] if 'title' in contract else None

        start_location, _ = Location.objects.get_or_create_from_esi(
            esi_client,
            contract['start_location_id']
        )
        end_location, _ = Location.objects.get_or_create_from_esi(
            esi_client,
            contract['end_location_id']
        )
        
        obj, created = Contract.objects.update_or_create(
            handler=handler,
            contract_id=contract['contract_id'],
            defaults={
                'acceptor': acceptor,
                'acceptor_corporation': acceptor_corporation,
                'collateral': contract['collateral'],
                'date_accepted': date_accepted,
                'date_completed': date_completed,
                'date_expired': contract['date_expired'],
                'date_issued': contract['date_issued'],
                'days_to_complete': contract['days_to_complete'],
                'end_location': end_location,
                'for_corporation': contract['for_corporation'],
                'issuer_corporation': issuer_corporation,
                'issuer': issuer,                                
                'reward': contract['reward'],
                'start_location': start_location,
                'status': contract['status'],
                'title': title,
                'volume': contract['volume'],
                'pricing': None,
                'issues': None
            }                        
        )
        return obj, created

    def update_pricing(self):
        """Updates contracts with matching pricing"""
        from .models import Pricing, Contract

        def _make_key(location_id_1: int, location_id_2: int) -> str:
            return '{}x{}'.format(int(location_id_1), int(location_id_2))

        pricings = dict()
        for x in Pricing.objects.filter(is_active=True).order_by('-id'):
            pricings[_make_key(x.start_location_id, x.end_location_id)] = x
            if x.is_bidirectional:
                pricings[_make_key(x.end_location_id, x.start_location_id)] = x

        for contract in self.all():
            if contract.status == Contract.STATUS_OUTSTANDING or not contract.pricing:
                with transaction.atomic():
                    route_key = _make_key(
                        contract.start_location_id, 
                        contract.end_location_id
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

    def send_notifications(self, force_sent=False, rate_limted=True):
        """Send notification about outstanding contracts that have pricing"""
        from .models import Contract

        add_tag = make_logger_prefix('send_notifications')
        logger.debug(add_tag('start'))

        # send pilot notifications
        if FREIGHT_DISCORD_WEBHOOK_URL:
            q = Contract.objects.filter(                
                status__exact=Contract.STATUS_OUTSTANDING,                
            ).exclude(pricing__exact=None)

            if not force_sent:
                q = q.filter(date_notified__exact=None)
            
            q = q.select_related()

            if q.count() > 0:
                logger.info(add_tag(
                    'Trying to send pilot notifications for'
                    + ' {} contracts'.format(q.count())
                ))
                
                for contract in q:
                    if not contract.has_expired:
                        contract.send_pilot_notification()
                        if rate_limted:
                            sleep(1)
                    else:
                        logger.debug(add_tag(
                            'contract {} has expired'.format(                                    
                                contract.contract_id
                            )
                        ))
        else:
            logger.debug(add_tag('FREIGHT_DISCORD_WEBHOOK_URL not configured'))

        # send customer notifications        
        if FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL:
            q = Contract.objects.filter(
                status__in=Contract.STATUS_FOR_CUSTOMER_NOTIFICATION,
            ).exclude(pricing__exact=None)
            
            q = q.select_related()

            if q.count() > 0:
                logger.debug(add_tag(
                    'Checking {} contracts if '.format(q.count())
                    + 'customer notifications need to be sent'
                ))
                for contract in q:
                    if contract.has_expired:
                        logger.debug(add_tag(
                            'contract {} has expired'.format(                                    
                                contract.contract_id
                            )
                        ))
                    elif contract.has_stale_status:
                        logger.debug(add_tag(
                            'contract {} has stale status'.format(                                    
                                contract.contract_id
                            )
                        ))
                    else:
                        contract.send_customer_notification(force_sent)
                        if rate_limted:
                            sleep(1)
        
        else:
            logger.debug(add_tag(
                'FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL not configured'
            ))
