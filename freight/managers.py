import logging
import json
from time import sleep

from bravado.exception import *

from django.db import models, transaction
from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCorporationInfo

from .app_settings import FREIGHT_DISCORD_WEBHOOK_URL
from .utils import LoggerAddTag, make_logger_prefix


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
            with transaction.atomic():
                pricing = None
                issues = None
                if contract.status==Contract.STATUS_OUTSTANDING:
                    route_key = _make_route_key(
                        contract.start_location_id, 
                        contract.end_location_id
                    )        
                    if route_key in pricings:
                        pricing = pricings[route_key]
                        issues = contract.get_price_check_issues(pricing)
                        if issues:
                            contract.issues = json.dumps(issues)
                        else:
                            contract.issues = None
                    
                contract.pricing = pricing

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

