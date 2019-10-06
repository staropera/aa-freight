import math
import datetime

from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.template import loader
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.utils.html import mark_safe

from allianceauth.authentication.models import CharacterOwnership
from esi.decorators import token_required
from esi.clients import esi_client_factory
from esi.models import Token
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter

from .models import *
from . import tasks
from .utils import get_swagger_spec_path, DATETIME_FORMAT, messages_plus


ADD_LOCATION_TOKEN_TAG = 'freight_add_location_token'
CALCULATOR_DATA = 'freight_calculator_data'

@login_required
@permission_required('freight.basic_access')
def index(request):
    return redirect('freight:calculator')


@login_required
@permission_required('freight.view_contracts')
def contract_list(request):
        
    context = {
        'page_title': 'Contracts'
    }        
    return render(request, 'freight/contract_list.html', context)


@login_required
@permission_required('freight.view_contracts')
def contract_list_data(request):
    """returns list of outstanding contracts for contract_list AJAX call"""
    contracts = Contract.objects.filter(
        handler__alliance__alliance_id=request.user.profile.main_character.alliance_id,
        status__in=[
            Contract.STATUS_OUTSTANDING,
            Contract.STATUS_IN_PROGRESS
        ]
    ).select_related()

    contracts_data = list()
    datetime_format = lambda x: x.strftime(DATETIME_FORMAT) if x else None
    character_format = lambda x: x.character_name if x else None
    for contract in contracts:                                
        has_pricing = contract.pricing is not None
        if has_pricing:
            errors = contract.get_pricing_errors(contract.pricing)            
        else:
            errors = None
        has_pricing_errors = errors is not None
        if has_pricing:            
            if not has_pricing_errors:
                glyph = 'ok'
                color = 'green'
                tooltip_text = contract.pricing.name
            else:
                glyph = 'warning-sign'
                color = 'red'                
                tooltip_text = '{}\n{}'.format(
                    contract.pricing.name, 
                    '\n'.join(errors)
                )
            pricing_check = ('<span class="glyphicon '
                + 'glyphicon-'+ glyph + '" ' 
                + 'aria-hidden="true" '
                + 'style="color:' + color + ' ;" ' 
                + 'data-toggle="tooltip" data-placement="top" '
                + 'title="' + tooltip_text + '">'
                + '</span>')
        else:
            pricing_check = 'N/A'

        contracts_data.append({
            'status': contract.status,
            'start_location': str(contract.start_location),
            'end_location': str(contract.end_location),
            'reward': '{:,.0f}'.format(contract.reward / 1000000),
            'collateral': '{:,.0f}'.format(contract.collateral / 1000000),
            'volume': '{:,.0f}'.format(contract.volume / 1000),
            'date_issued': datetime_format(contract.date_issued),
            'date_expired': datetime_format(contract.date_expired),
            'issuer': character_format(contract.issuer),
            'date_accepted': datetime_format(contract.date_accepted),
            'acceptor': character_format(contract.acceptor),
            'has_pricing': has_pricing,
            'has_pricing_errors': has_pricing_errors,
            'pricing_check': pricing_check
        })

    return JsonResponse(contracts_data, safe=False)


@login_required
@permission_required('freight.use_calculator')
def calculator(request):            
    from .forms import CalculatorForm
    if request.method != 'POST':
        form = CalculatorForm()
        price = None        

    else:
        form = CalculatorForm(request.POST)
        request.POST._mutable = True
        
        if form.is_valid():                                    
            pricing = form.cleaned_data['pricing']
            volume = int(form.cleaned_data['volume'])
            collateral = int(form.cleaned_data['collateral'])        
            price = math.ceil((pricing.get_calculated_price(
                volume * 1000,
                collateral * 1000000) 
                / 1000000) * 1000000
            )            
                
        else:
            price = None
        
    if price:
        request.session[CALCULATOR_DATA] = {
            'volume': volume * 1000,
            'collateral': collateral * 1000000,
            'reward': price
        }
    else:
        request.session[CALCULATOR_DATA] = None

    return render(
        request, 'freight/calculator.html', 
        {
            'page_title': 'Reward Calculator',            
            'form': form, 
            'price': price,            
        }
    )


@login_required
@permission_required('freight.use_calculator')
def calculator_pricing_info(request, pricing_pk):
    try:
        pricing = Pricing.objects.get(pk=pricing_pk)
    except:
        pricing = None
    return render(
        request, 
        'freight/calculator_pricing_info.html', 
        {            
            'pricing': pricing
        }
    )


@login_required
@permission_required('freight.use_calculator')
def calculator_contract_info(request, pricing_pk):
    try:
        pricing = Pricing.objects.get(pk=pricing_pk)        
        contract = request.session[CALCULATOR_DATA]
        if pricing.days_to_expire:
            expires_on = datetime.datetime.now(
                datetime.timezone.utc
            )  + datetime.timedelta(days=pricing.days_to_expire)
        else:
            expires_on = None
    except:
        pricing = None
        contract = None
        expires_on = None
    return render(
        request, 
        'freight/calculator_contract_info.html', 
        {            
            'contract': contract,
            'pricing': pricing,
            'expires_on': expires_on,
        }
    )


@login_required
@permission_required('freight.setup_contract_handler')
@token_required(scopes=ContractHandler.get_esi_scopes())
def create_or_update_service(request, token):
    success = True
    token_char = EveCharacter.objects.get(character_id=token.character_id)

    if token_char.alliance_id is None:
        messages_plus.warning(
            request, 
            'Can not setup contract handler, '
            'because {} is not a member of any alliance'.format(token_char)
        )
        success = False
    
    if success:
        try:
            owned_char = CharacterOwnership.objects.get(
                user=request.user,
                character=token_char
            )            
        except CharacterOwnership.DoesNotExist:
            messages_plus.warning(
                request,
                'Could not find character {}'.format(token_char.character_name)    
            )
            success = False
    
    if success:
        try:
            alliance = EveAllianceInfo.objects.get(
                alliance_id=token_char.alliance_id
            )
        except EveAllianceInfo.DoesNotExist:
            alliance = EveAllianceInfo.objects.create_alliance(
                token_char.alliance_id
            )
            alliance.save()

    if success:
        contract_handler = ContractHandler.objects.first()
        if contract_handler and contract_handler.alliance != alliance:
            messages_plus.error(
                request,
                'There already is a contract handler installed for a '
                + 'different alliance. You need to first delete the '
                + 'existing contract handler in the admin section '
                + 'before you can set up this app for a different alliance.'
            )
            success = False
    
    if success:
        contract_handler, created = ContractHandler.objects.update_or_create(
            alliance=alliance,
            defaults={
                'character': owned_char
            }
        )          
        tasks.run_contracts_sync.delay(            
            force_sync=True,
            user_pk=request.user.pk
        )        
        messages_plus.success(
            request, 
            'Contract Handler setup completed for '
            + '<strong>{}</strong> alliance '.format(alliance.alliance_name)
            + 'with <strong>{}</strong> as sync character. '.format(
                    contract_handler.character.character.character_name, 
                )
            + 'Started syncing of courier contracts. '
            + 'You will receive a report once it is completed.'
        )
    return redirect('freight:index')


@login_required
@token_required(scopes=Location.get_esi_scopes())
@permission_required('freight.add_location')
def add_location(request, token): 
    request.session[ADD_LOCATION_TOKEN_TAG] = token.pk
    return redirect('freight:add_location_2')


@login_required
@permission_required('freight.add_location')
def add_location_2(request): 
    from .forms import AddLocationForm
    
    if ADD_LOCATION_TOKEN_TAG not in request.session:
        raise RuntimeError('Missing token in session')
    else:
        token = Token.objects.get(pk=request.session[ADD_LOCATION_TOKEN_TAG])
    
    if request.method != 'POST':
        form = AddLocationForm()
        
    else:
        form = AddLocationForm(request.POST)
        if form.is_valid():
            location_id = form.cleaned_data['location_id']
            try:                
                client = esi_client_factory(
                    token=token, 
                    spec_file=get_swagger_spec_path()
                )
            
                location, created = Location.objects.update_or_create_esi(
                    client, 
                    location_id,
                    add_unknown=False
                )
                action_txt = 'Added' if created else 'Updated'
                messages_plus.success(
                    request,
                    '{} "{}"'.format(
                        action_txt,                        
                        location.name
                    )
                )
                return redirect('freight:add_location_2')    

            except Exception as ex:
                messages_plus.warning(
                    request,
                    'Failed to add location with token from {}'.format(token.character_name)
                    + ' for location ID {}: '. format(location_id)
                    + '{}'.format(type(ex).__name__)
                )
            
        
    return render(
        request, 'freight/add_location.html', 
        {            
            'page_title': 'Add / Update Location',
            'form': form,
            'token_char_name': token.character_name
        }
    )