import logging
from bravado.exception import *
from django.db import models
from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCorporationInfo
from .utils import LoggerAddTag, makeLoggerPrefix


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
            location = Location.objects.get(id=location_id)
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

        addPrefix = makeLoggerPrefix(location_id)

        if (location_id >= self.STATION_ID_START 
                and location_id <= self.STATION_ID_END):
            logger.info(addPrefix('Fetching station from ESI'))
            try:
                station = client.Universe.get_universe_stations_station_id(
                    station_id=location_id
                ).result()
                location, created = Location.objects.update_or_create(
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
                location, created = Location.objects.update_or_create(
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
                    location, created = Location.objects.get_or_create(
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