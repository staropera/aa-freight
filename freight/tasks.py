import logging
import os
import datetime
import hashlib
import json
from celery import shared_task
from django.db import transaction
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from allianceauth.authentication.models import CharacterOwnership
from allianceauth.notifications import notify
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter
from esi.clients import esi_client_factory
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token
from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path
from .models import *

logger = LoggerAddTag(logging.getLogger(__name__), __package__)

"""
Swagger Operations:
get_universe_structures_structure_id
get_corporation_corporation_id
"""


@shared_task
def sync_contracts(contracts_handler_pk, force_sync = False, user_pk = None):
    try:
        handler = ContractHandler.objects.get(pk=contracts_handler_pk)
    except ContractHandler.DoesNotExist:        
        raise ContractHandler.DoesNotExist(
            'task called for non jf service with pk {}'.format(contracts_handler_pk)
        )
        return False
    
    try:
        add_prefix = make_logger_prefix(handler)
        alliance_name = handler.alliance.alliance_name
        
        if handler.character is None:
            logger.error(add_prefix(
                'No character configured to sync the alliance'
            ))           
            raise ValueError()

        # abort if character does not have sufficient permissions
        if not handler.character.user.has_perm(
                'freight.add_syncmanager'
            ):
            logger.error(add_prefix(
                'Character does not have sufficient permission '
                + 'to sync contracts'
            ))            
            raise ValueError()

        try:            
            # get token    
            token = Token.objects.filter(
                user=handler.character.user, 
                character_id=handler.character.character.character_id
            ).require_scopes(
                ContractHandler.get_esi_scopes()
            ).require_valid().first()
        except TokenInvalidError:        
            logger.error(add_prefix(
                'Invalid token'
            ))            
            raise TokenInvalidError()
            
        except TokenExpiredError:            
            logger.error(add_prefix(
                'Token expired'
            ))
            raise TokenExpiredError()
        
        # fetching data from ESI
        logger.info(add_prefix('Fetching alliance contracts from ESI - page 1'))
        client = esi_client_factory(
            token=token, 
            spec_file=get_swagger_spec_path()
        )

        # get contracts from first page
        operation = client.Contracts.get_corporations_corporation_id_contracts(
            corporation_id=handler.character.character.corporation_id
        )
        operation.also_return_response = True
        contracts_all, response = operation.result()
        pages = int(response.headers['x-pages'])
        
        # add contracts from additional pages if any            
        for page in range(2, pages + 1):
            logger.info(add_prefix(
                'Fetching alliance contracts from ESI - page {}'.format(page)
            ))
            contracts_all += client.Contracts.get_corporations_corporation_id_contracts(
                corporation_id=handler.character.character.corporation_id,
                page=page
            ).result()

        # filter out relevant contracts
        contracts = [
            x for x in contracts_all 
            if x['type'] == 'courier' 
            and int(x['assignee_id']) == int(handler.alliance.alliance_id)
        ]

        # determine if contracts have changed by comparing their hashes
        new_version_hash = hashlib.md5(
            json.dumps(contracts, cls=DjangoJSONEncoder).encode('utf-8')
        ).hexdigest()
        if force_sync or new_version_hash != handler.version_hash:
            logger.info(add_prefix(
                'Storing alliance update with {:,} contracts'.format(
                    len(contracts)
                ))
            )                
            
            with transaction.atomic():                
                for contract in contracts:                    
                    if int(contract['acceptor_id']) != 0:
                        try:
                            acceptor = EveCharacter.objects.get(
                                character_id=contract['acceptor_id']
                            )
                        except EveAllianceInfo.DoesNotExist:
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
                    
                    date_accepted = getattr(contract, 'date_accepted', None)
                    date_completed = getattr(contract, 'date_completed', None)
                    title = getattr(contract, 'title', None)

                    start_location, _ = Location.objects.get_or_create_esi(
                        client,
                        contract['start_location_id']
                    )
                    end_location, _ = Location.objects.get_or_create_esi(
                        client,
                        contract['end_location_id']
                    )
                    
                    Contract.objects.update_or_create(
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
                            'price': contract['price'],
                            'reward': contract['reward'],
                            'start_location': start_location,
                            'status': contract['status'],
                            'title': title,
                            'volume': contract['volume'],
                        }                        
                    )
                handler.version_hash = new_version_hash
                handler.last_sync = datetime.datetime.now(
                    datetime.timezone.utc
                )
                handler.save()
                success = True
            
        else:
            logger.info(add_prefix('Alliance contracts are unchanged.'))
            success = True
        
    
    except Exception as ex:
            logger.error(add_prefix(
                'An unexpected error ocurred'. format(ex)
            ))
            error_code = type(ex).__name__
            success = False

    if user_pk:
        try:
            message = 'Syncing of alliance contracts for "{}" {}.\n'.format(
                handler.alliance,
                'completed successfully' if success else 'has failed'
            )
            if success:
                message += '{:,} contracts synced.'.format(
                    handler.contract_set.count()
                )
            else:
                message += 'Error code: {}'.format(error_code)
            
            notify(
                user=User.objects.get(pk=user_pk),
                title='Freight: Contracts sync for {}: {}'.format(
                    handler.alliance,
                    'OK' if success else 'FAILED'
                ),
                message=message,
                level='success' if success else 'danger'
            )
        except Exception as ex:
            logger.error(add_prefix(
                'An unexpected error ocurred while trying to '
                + 'report to user: {}'. format(ex)
            ))
    
    return success