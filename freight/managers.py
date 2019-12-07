import logging
import json
from time import sleep

from bravado.exception import *

from django.db import models, transaction
from django.utils.timezone import now

from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo

from .app_settings import *
from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path, \
    make_logger_prefix


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class LocationManager(models.Manager):
    STATION_ID_START = 60000000
    STATION_ID_END = 69999999
    
    def get_or_create_esi(
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
            location, created = self.update_or_create_esi(
                esi_client, 
                location_id,
                add_unknown
            )
        
        return location, created


    def update_or_create_esi(
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
                station = esi_client.Universe.get_universe_stations_station_id(
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
                logger.warn(addPrefix(
                    'Failed to load station: '.format(ex)
                ))
                raise ex
            
        else:
            logger.info(addPrefix('Fetching structure from ESI'))
            try:
                structure = esi_client.Universe.get_universe_structures_structure_id(
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
                        id = location_id,
                        defaults={
                            'name': 'Unknown structure {}'.format(location_id),
                            'category_id': Location.CATEGORY_STRUCTURE_ID
                        }
                    )
                else:
                    raise ex
            except Exception as ex:
                logger.warn(addPrefix(
                    'Failed to load structure: '.format(ex)
                ))      
                raise ex
       
        return location, created


class EveOrganizationManager(models.Manager):
    
    def get_or_create_esi(
            self,             
            organization_id: int
        ) -> list:
        """gets or creates organization object with data fetched from ESI"""
        from .models import EveOrganization
        try:
            organization = self.get(id=organization_id)
            created = False
        except EveOrganization.DoesNotExist:
            organization, created = self.update_or_create_esi(organization_id)
        
        return organization, created


    def update_or_create_esi(
            self,             
            organization_id: int
        ) -> list:
        """updates or creates organization object with data fetched from ESI"""
        from .models import EveOrganization

        addPrefix = make_logger_prefix(organization_id)
        
        logger.info(addPrefix('Fetching organization from ESI'))
        try:
            esi_client = esi_client_factory(spec_file=get_swagger_spec_path())
            response = esi_client.Universe.post_universe_names(
                ids=[organization_id]
            ).result()
            if len(response) != 1:
                raise RuntimeError('ESI did not find any entity with this ID')            
            else:
                organization_data = response[0]
            organization, created = self.update_or_create(
                id=organization_data['id'],
                defaults={
                    'name': organization_data['name'],
                    'category': organization_data['category'],
                }
            ) 
        except Exception as ex:
            logger.warn(addPrefix(
                'Failed to load organization from ESI: '.format(ex)
            ))
            raise ex
        
       
        return organization, created


    def update_or_create_from_evecharacter(
            self,             
            character: EveCharacter,
            category: str
        ) -> list:
        """updates or creates organization object from an evecharacter object"""
        from .models import EveOrganization
        
        addPrefix = make_logger_prefix(character.character_id)

        try:            
            if category == EveOrganization.CATEGORY_ALLIANCE:            
                if not character.alliance_id:
                    raise ValueError('character is not an alliance member')
                organization, created = self.update_or_create(
                    id=character.alliance_id,
                    defaults={
                        'name': character.alliance_name,
                        'category': EveOrganization.CATEGORY_ALLIANCE,
                    }
                )
            elif category == EveOrganization.CATEGORY_CORPORATION:
                organization, created = self.update_or_create(
                    id=character.corporation_id,
                    defaults={
                        'name': character.corporation_name,
                        'category': EveOrganization.CATEGORY_CORPORATION,
                    }
                )
            else:
                raise ValueError('Invalid category: {}'. format(category))
        except Exception as ex:
            logger.warn(addPrefix(
                'Failed to load organization from ESI: '.format(ex)
            ))
            raise ex

        return organization, created


class ContractManager(models.Manager):
    
    def update_or_create_from_dict(
        self, 
        handler: object, 
        contract: dict, 
        esi_client: object
    ):
        """updates or creates a contract from given dict"""

        from .models import Contract, Location

        if int(contract['acceptor_id']) != 0:
            try:
                acceptor = EveCharacter.objects.get(
                    character_id=contract['acceptor_id']
                )
            except EveCharacter.DoesNotExist:
                acceptor = EveCharacter.objects.create_character(
                    character_id=contract['acceptor_id']
                )
        else:
            acceptor = None

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

        start_location, _ = Location.objects.get_or_create_esi(
            esi_client,
            contract['start_location_id']
        )
        end_location, _ = Location.objects.get_or_create_esi(
            esi_client,
            contract['end_location_id']
        )
        
        obj, created = Contract.objects.update_or_create(
            handler=handler,
            contract_id=contract['contract_id'],
            defaults={
                'acceptor': acceptor,
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
        """Updates pricing relation for all contracts"""
        from .models import Pricing, Contract

        def _make_route_key(location_id_1: int, location_id_2: int) -> str:
            return "x".join([str(x) for x in sorted([location_id_1, location_id_2])])

        pricings = {
            _make_route_key(x.start_location_id, x.end_location_id): x 
            for x in Pricing.objects.filter(active__exact=True) 
        }

        for contract in self.all():
            if contract.status == Contract.STATUS_OUTSTANDING or not contract.pricing:
                with transaction.atomic():
                    route_key = _make_route_key(
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


    def send_notifications(self, force_sent = False, rate_limted = True):
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
                        )))
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
                    if not contract.has_expired:
                        contract.send_customer_notification(force_sent)
                        if rate_limted:
                            sleep(1)
                    else:
                        logger.debug(add_tag(
                            'contract {} has expired'.format(                                    
                                contract.contract_id
                        )))
        
        else:
            logger.debug(add_tag(
                'FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL not configured'
            ))