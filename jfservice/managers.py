from django.db import models
from esi.clients import esi_client_factory
from allianceauth.eveonline.models import EveCorporationInfo

class LocationManager(models.Manager):

    EVE_STRUCTURE_ID_START = 1000000000000
    
    def update_or_create_smart(self, client, location_id):
        from .models import Structure, Location

        if location_id >= self.EVE_STRUCTURE_ID_START:
            structure_info = client.Universe.get_universe_structures_structure_id(
                structure_id=location_id
            ).result()
            try:
                owner = EveCorporationInfo.objects.get(
                    corporation_id=structure_info['owner_id']
                )
            except EveCorporationInfo.DoesNotExist:
                owner = EveCorporationInfo.objects.create_corporation(
                    corp_id=structure_info['owner_id']
                )
            structure, _ = Structure.objects.update_or_create(
                id=location_id,
                defaults={
                    'name': structure_info['name'],
                    'owner': owner,
                    'position_x': structure_info['position']['x'],
                    'position_y': structure_info['position']['y'],
                    'position_z': structure_info['position']['z'],
                    'solar_system_id': structure_info['solar_system_id'],
                    'type_id': structure_info['type_id'],
                }
            )
            location, created = Location.objects.update_or_create(
                id = location_id,
                defaults={
                    'structure': structure
                }
            )
        else:
            location, created = Location.objects.update_or_create(
                id = location_id,
                defaults={
                    'item_id': location_id
                }
            )
        return location, created