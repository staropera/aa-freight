import math

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
from .forms import CalculatorForm, AddLocationForm
from .utils import get_swagger_spec_path, DATETIME_FORMAT, messages_nice

ADD_LOCATION_TOKEN_TAG = 'jfservice_add_location_token'

@login_required
@permission_required('jfservice.access_jfservice')
def index(request):
    return redirect('jfservice:calculator')


@login_required
@permission_required('jfservice.access_jfservice')
def contract_list(request):
        
    context = {
        'page_title': 'Contracts'
    }        
    return render(request, 'jfservice/contract_list.html', context)


@login_required
@permission_required('jfservice.access_jfservice')
def contract_list_data(request):

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
        })

    return JsonResponse(contracts_data, safe=False)


@login_required
@permission_required('jfservice.access_jfservice')
def calculator(request):            
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
            
            errors = pricing.get_contract_pricing_errors(
                volume * 1000,
                collateral * 1000000                
            )
            for error in errors:            
                messages_nice.error(
                    request,                     
                    'Invalid input: {}'.format(error)                    
                )

            if not errors:
                price = math.ceil((pricing.get_calculated_price(
                    volume * 1000,
                    collateral * 1000000) 
                    / 1000000) * 1000000
                )
            else:
                price = None
        else:
            price = None
        
    return render(
        request, 'jfservice/calculator.html', 
        {
            'page_title': 'Price Calculator',            
            'form': form, 
            'price': price,            
        }
    )


@login_required
@permission_required('jfservice.access_jfservice')
def calculator_pricing_info(request, pricing_pk):
    pricing = Pricing.objects.get(pk=pricing_pk)    
    return render(
        request, 
        'jfservice/calculator_pricing_info.html', 
        {'pricing': pricing}
    )
    

@login_required
@permission_required('jfservice.access_jfservice')
@token_required(scopes=ContractsHandler.get_esi_scopes())
def create_or_update_service(request, token):
    success = True
    token_char = EveCharacter.objects.get(character_id=token.character_id)

    if token_char.alliance_id is None:
        messages_nice.warning(
            request, 
            'Can not create JF service, because {} is not a member of any '
                + 'alliance. '.format(token_char)            
        )
        success = False
    
    if success:
        try:
            owned_char = CharacterOwnership.objects.get(
                user=request.user,
                character=token_char
            )            
        except CharacterOwnership.DoesNotExist:
            messages_nice.warning(
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
        contracts_handler, created = ContractsHandler.objects.update_or_create(    
            alliance=alliance,
            defaults={
                'character': owned_char
            }
        )          
        tasks.sync_contracts.delay(
            contracts_handler_pk=contracts_handler.pk,
            force_sync=True,
            user_pk=request.user.pk
        )        
        messages_nice.success(
            request, 
            'JF service created for {} alliance with {} as sync character. '.format(                    
                    alliance.alliance_name,
                    contracts_handler.character.character.character_name, 
                )
            + 'Started syncing of courier contracts. '
            + 'You will receive a report once it is completed.'
        )
    return redirect('jfservice:index')


@login_required
@token_required(scopes=Location.get_esi_scopes())
@permission_required('jfservice.access_jfservice')
def add_location(request, token): 
    request.session[ADD_LOCATION_TOKEN_TAG] = token.pk
    return redirect('jfservice:add_location_2')


@login_required
@permission_required('jfservice.access_jfservice')
def add_location_2(request): 
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
                messages_nice.success(
                    request,
                    '{} "{}"'.format(
                        action_txt,                        
                        location.name
                    )
                )
                return redirect('jfservice:add_location_2')    

            except Exception as ex:
                messages_nice.warning(
                    request,
                    'Failed to add location with token from {}'.format(token.character_name)
                    + ' for location ID {}: '. format(location_id)
                    + '{}'.format(type(ex).__name__)
                )
            
        
    return render(
        request, 'jfservice/add_location.html', 
        {            
            'page_title': 'Add / Update Location',
            'form': form,
            'token_char_name': token.character_name
        }
    )