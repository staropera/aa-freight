import logging
import json
from time import sleep

from bravado.exception import *

from django.db import models, transaction
from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCharacter

from .app_settings import FREIGHT_DISCORD_WEBHOOK_URL
from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class LocationManager(models.Manager):
    STATION_ID_START = 60000000
    STATION_ID_END = 69999999
    
    def get_or_create_esi(
            self, 
            client: object, 
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
                client, 
                location_id,
                add_unknown
            )
        
        return location, created


    def update_or_create_esi(
            self, 
            client: object, 
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
                station = client.Universe.get_universe_stations_station_id(
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
                structure = client.Universe.get_universe_structures_structure_id(
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
            client = esi_client_factory(spec_file=get_swagger_spec_path())
            response = client.Universe.post_universe_names(
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

    def send_notifications(self, force_sent = False):
        """Send notification about outstanding contracts that have pricing"""
        from .models import Contract

        if FREIGHT_DISCORD_WEBHOOK_URL:
            q = Contract.objects.filter(                
                status__exact=Contract.STATUS_OUTSTANDING,                
            ).exclude(pricing__exact=None)

            if not force_sent:
                q = q.filter(date_notified__exact=None)
            
            q = q.select_related()

            if q.count() > 0:
                logger.info('Trying to send notifications for {} contracts'.format(
                    q.count()
                ))
                
                for contract in q:
                    contract.send_notification()
                    sleep(1)
            else:
                logger.info('No new contracts to notify about')
        
        else:
            logger.info('Discord webhook not configured - skipping sending notifications')

