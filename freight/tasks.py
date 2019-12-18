import logging
import os
import datetime
import hashlib
import json

from celery import shared_task

from django.db import transaction
from django.conf import settings
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.notifications import notify
from allianceauth.eveonline.models import EveCorporationInfo, EveCharacter
from esi.clients import esi_client_factory
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token

from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path
from .models import *


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


@shared_task
def run_contracts_sync(force_sync = False, user_pk = None):
    
    try:
        handler = ContractHandler.objects.first()
        if not handler:
            logger.info(
                'could not sync contracts because no contract handler was found'
            )
            return False

        handler.last_sync = datetime.datetime.now(datetime.timezone.utc)
        handler.save()

        add_prefix = make_logger_prefix(handler)

        # abort if operation mode from settings is different
        if handler.operation_mode != FREIGHT_OPERATION_MODE:
            logger.error(add_prefix(
                'Current operation mode not matching the handler'
            ))           
            handler.last_error = ContractHandler.ERROR_OPERATION_MODE_MISMATCH
            handler.save()
            raise ValueError()
                
        # abort if character is not configured
        if handler.character is None:
            logger.error(add_prefix(
                'No character configured to sync'
            ))           
            handler.last_error = ContractHandler.ERROR_NO_CHARACTER
            handler.save()
            raise ValueError()

        # abort if character does not have sufficient permissions
        if not handler.character.user.has_perm(
                'freight.setup_contract_handler'
            ):
            logger.error(add_prefix(
                'Character does not have sufficient permission '
                + 'to sync contracts'
            ))            
            handler.last_error = ContractHandler.ERROR_INSUFFICIENT_PERMISSIONS
            handler.save()
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
                'Invalid token for fetching contracts'
            ))            
            handler.last_error = ContractHandler.ERROR_TOKEN_INVALID
            handler.save()
            raise TokenInvalidError()
            
        except TokenExpiredError:            
            logger.error(add_prefix(
                'Token expired for fetching contracts'
            ))
            handler.last_error = ContractHandler.ERROR_TOKEN_EXPIRED
            handler.save()
            raise TokenExpiredError()
        
        else:
            if not token:
                logger.error(add_prefix('No valid token found'))            
                handler.last_error = ContractHandler.ERROR_TOKEN_INVALID
                handler.save()
                raise TokenInvalidError()
        
        try:
            # fetching data from ESI
            logger.info(add_prefix(
                'Fetching contracts from ESI - page 1'
            ))
            esi_client = esi_client_factory(
                token=token, 
                spec_file=get_swagger_spec_path()
            )

            # get contracts from first page
            operation = esi_client.Contracts\
                .get_corporations_corporation_id_contracts(
                    corporation_id=\
                        handler.character.character.corporation_id
                )
            operation.also_return_response = True
            contracts_all, response = operation.result()
            pages = int(response.headers['x-pages'])
            
            # add contracts from additional pages if any            
            for page in range(2, pages + 1):
                logger.info(add_prefix(
                    'Fetching contracts from ESI - page {}'.format(page)
                ))
                contracts_all += esi_client.Contracts\
                    .get_corporations_corporation_id_contracts(
                        corporation_id=handler\
                            .character.character.corporation_id,
                        page=page
                    ).result()
            
            if settings.DEBUG:
                # store to disk (for debugging)
                with open('contracts_raw.json', 'w', encoding='utf-8') as f:
                    json.dump(
                        contracts_all, 
                        f, 
                        cls=DjangoJSONEncoder, 
                        sort_keys=True, 
                        indent=4
                    )
                        
            # 1st filter: reduce to courier contracts assigned to handler org
            contracts_courier = [
                x for x in contracts_all 
                if x['type'] == 'courier' 
                and int(x['assignee_id']) == int(handler.organization.id)
            ]

            # 2nd filter: remove contracts not in scope due to operation mode
            contracts = list()
            for contract in contracts_courier:
                try:
                    issuer = EveCharacter.objects.get(
                        character_id=contract['issuer_id']
                    )
                except EveCharacter.DoesNotExist:
                    issuer = EveCharacter.objects.create_character(
                        character_id=contract['issuer_id']
                    )
                
                assignee_id = int(contract['assignee_id'])
                issuer_corporation_id = int(issuer.corporation_id)
                issuer_alliance_id = int(issuer.alliance_id) \
                    if issuer.alliance_id else None
                
                if handler.operation_mode == FREIGHT_OPERATION_MODE_MY_ALLIANCE:
                    in_scope = issuer_alliance_id == assignee_id
                
                elif handler.operation_mode == FREIGHT_OPERATION_MODE_MY_CORPORATION:
                    in_scope = assignee_id == issuer_corporation_id
                
                elif handler.operation_mode == FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE:
                    in_scope = (issuer_alliance_id ==
                        int(handler.character.character.alliance_id))

                elif handler.operation_mode == FREIGHT_OPERATION_MODE_CORP_PUBLIC:
                    in_scope = True
                
                else:
                    raise NotImplementedError(
                        'Unsupported operation mode: {}'.format(
                            handler.operation_mode
                        )
                    )
                if in_scope:
                    contracts.append(contract)

            # determine if contracts have changed by comparing their hashes
            new_version_hash = hashlib.md5(
                json.dumps(contracts, cls=DjangoJSONEncoder).encode('utf-8')
            ).hexdigest()
            if (force_sync 
                or new_version_hash != handler.version_hash
            ):
                logger.info(add_prefix(
                    'Storing update with {:,} contracts'.format(
                        len(contracts)
                    ))
                )
                
                # update contracts in local DB
                with transaction.atomic():                
                    handler.version_hash = new_version_hash
                    no_errors = True
                    for contract in contracts:                    
                        try:
                            Contract.objects.update_or_create_from_dict(
                                handler=handler,
                                contract=contract,
                                esi_client=esi_client
                            )
                        except Exception as ex:
                            logger.exception(add_prefix(
                                'An unexpected error ocurred ' \
                                + 'while trying to load contract '\
                                + '{}: {}'. format(
                                    contract['contract_id'] \
                                        if 'contract_id' in contract \
                                        else 'Unknown',
                                    ex
                                )
                            ))
                            no_errors = False                
                    
                    if no_errors:
                        handler.last_error = ContractHandler.ERROR_NONE
                    else:
                        handler.last_error = ContractHandler.ERROR_UNKNOWN
                    handler.save()

                Contract.objects.update_pricing()

            else:
                logger.info(add_prefix('Contracts are unchanged.'))

            send_contract_notifications.delay()
            
        except Exception as ex:
                logger.exception(add_prefix(
                    'An unexpected error ocurred {}'. format(ex)
                ))                                
                handler.last_error = ContractHandler.ERROR_UNKNOWN
                handler.save()
                raise ex

    except Exception as ex:
        success = False
        error_code = type(ex).__name__
        
    else:
        success = True

    if user_pk:
        try:
            message = 'Syncing of contracts for "{}"'.format(
                handler.organization.name
            )
            message += ' in operation mode "{}" {}.\n'.format(
                handler.operation_mode_friendly,
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
                    handler.organization.name,
                    'OK' if success else 'FAILED'
                ),
                message=message,
                level='success' if success else 'danger'
            )
        except Exception as ex:
            logger.exception(add_prefix(
                'An unexpected error ocurred while trying to '
                + 'report to user: {}'. format(ex)
            ))
    
    return success


@shared_task
def send_contract_notifications(force_sent = False, rate_limted = True):
    """Send notification about outstanding contracts that have pricing"""
      
    try:
        Contract.objects.send_notifications(force_sent, rate_limted)
        success = True

    except Exception as ex:
        logger.exception('An unexpected error ocurred: {}'.format(ex))        
        success = False        

    return success


@shared_task
def update_contracts_pricing():
    
    logger.info('Started updating contracts pricing')
    
    try:    
        Contract.objects.update_pricing()        
        success = True

    except Exception as ex:
        logger.exception('An unexpected error ocurred: {}'.format(ex))        
        success = False        

    return success