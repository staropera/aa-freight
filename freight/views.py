import datetime
import json
import math

import pytz

from django.forms import HiddenInput
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, Http404, JsonResponse
from django.db.models import Count, Sum, Q
from django.shortcuts import render, redirect
from django.template import loader
from django.utils.html import mark_safe

from allianceauth.authentication.models import CharacterOwnership
from esi.decorators import token_required
from esi.clients import esi_client_factory
from esi.models import Token
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter

from . import tasks
from .app_settings import get_freight_operation_mode_friendly, FREIGHT_STATISTICS_MAX_DAYS
from .models import *
from .utils import get_swagger_spec_path, DATETIME_FORMAT, messages_plus


ADD_LOCATION_TOKEN_TAG = 'freight_add_location_token'
CONTRACT_LIST_USER = 'user'
CONTRACT_LIST_ACTIVE = 'active'


@login_required
@permission_required('freight.basic_access')
def index(request):
    return redirect('freight:calculator')


@login_required
@permission_required('freight.view_contracts')
def contract_list_active(request):
        
    context = {
        'page_title': 'Active Contracts',
        'category': CONTRACT_LIST_ACTIVE
    }        
    return render(request, 'freight/contract_list.html', context)


@login_required
@permission_required('freight.use_calculator')
def contract_list_user(request):
        
    context = {
        'page_title': 'My Contracts',
        'category': CONTRACT_LIST_USER
    }        
    return render(request, 'freight/contract_list.html', context)


@login_required
@permission_required('freight.basic_access')
def contract_list_data(request, category):
    """returns list of outstanding contracts for contract_list AJAX call"""
    
    if category == CONTRACT_LIST_ACTIVE:
        if not request.user.has_perm('freight.view_contracts'):
            raise RuntimeError('Insufficient permissions')
        else:            
            contracts = Contract.objects.filter(                
                status__in=[
                    Contract.STATUS_OUTSTANDING,
                    Contract.STATUS_IN_PROGRESS
                ]
            ).select_related()
    elif category == CONTRACT_LIST_USER:
        if not request.user.has_perm('freight.use_calculator'):
            raise RuntimeError('Insufficient permissions')
        else:
            user_characters = [x.character for x in request.user.character_ownerships.select_related().all()]
            contracts = Contract.objects.filter(
                issuer__in=user_characters
            ).select_related()
    else:
        raise ValueError('Invalid category: {}'.format(category))

    create_glyph_html = lambda glyph, tooltip_text, color = 'initial': \
        ('<span class="glyphicon '
        + 'glyphicon-'+ glyph + '" ' 
        + 'aria-hidden="true" '
        + 'style="color:' + color + ' ;" ' 
        + 'data-toggle="tooltip" data-placement="top" '
        + 'title="' + tooltip_text + '">'
        + '</span>')

    contracts_data = list()
    datetime_format = lambda x: x.strftime(DATETIME_FORMAT) if x else None
    character_format = lambda x: x.character_name if x else None
    for contract in contracts:                                        
        if contract.has_pricing:            
            route_name = contract.pricing.name
            if not contract.has_pricing_errors:
                glyph = 'ok'
                color = 'green'
                tooltip_text = route_name
            else:
                glyph = 'warning-sign'
                color = 'red'                
                tooltip_text = '{}\n{}'.format(
                    route_name, 
                    '\n'.join(json.loads(contract.issues))
                )
            pricing_check = create_glyph_html(glyph, tooltip_text, color)
        else:
            route_name = ''
            pricing_check = '-'
        
        if contract.title:
            notes = create_glyph_html('envelope', contract.title)
        else:
            notes = ''
        
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
            'notes': notes,
            'date_accepted': datetime_format(contract.date_accepted),
            'acceptor': character_format(contract.acceptor),
            'has_pricing': contract.has_pricing,
            'has_pricing_errors': contract.has_pricing_errors,
            'pricing_check': pricing_check,
            'route_name': route_name,
            'is_in_progress': contract.is_in_progress,
            'is_failed': contract.is_failed,
            'is_completed': contract.is_completed,            
        })

    return JsonResponse(contracts_data, safe=False)


@login_required
@permission_required('freight.use_calculator')
def calculator(request, pricing_pk = None):            
    from .forms import CalculatorForm
    if request.method != 'POST':
        if pricing_pk:
            try:
                pricing = Pricing.objects.filter(active__exact=True).get(pk=pricing_pk)
            except Pricing.DoesNotExist:
                pricing = Pricing.objects.filter(active__exact=True).first()
        else:            
            pricing = Pricing.objects.filter(active__exact=True).first()
        form = CalculatorForm(initial={'pricing': pricing})
        price = None        

    else:
        form = CalculatorForm(request.POST)
        request.POST._mutable = True

        try:
            pricing = Pricing.objects.filter(active__exact=True).get(pk=form.data['pricing'])
        except Pricing.DoesNotExist:
            pricing = Pricing.objects.filter(active__exact=True).first()
        
        if form.is_valid():                                    
            # pricing = form.cleaned_data['pricing']
            if form.cleaned_data['volume']:
                volume = int(form.cleaned_data['volume'])
            else:
                volume = 0
            if form.cleaned_data['collateral']:
                collateral = int(form.cleaned_data['collateral'])        
            else:
                collateral = 0
            price = math.ceil(pricing.get_calculated_price(
                    volume * 1000, 
                    collateral * 1000000
                ) / 1000000
            ) * 1000000
                
        else:
            price = None            

    if pricing:
        if not pricing.requires_volume():
            form.fields['volume'].widget = HiddenInput()
        if not pricing.requires_collateral():
            form.fields['collateral'].widget = HiddenInput()
    
    if price:
        if pricing.days_to_expire:
            expires_on = datetime.datetime.now(
                datetime.timezone.utc
            )  + datetime.timedelta(days=pricing.days_to_expire)
        else:
            expires_on = None
    else:
        collateral = None
        volume = None
        expires_on = None

    handler = ContractHandler.objects.first()
    if handler:
        organization_name = handler.organization.name
        availability = get_freight_operation_mode_friendly(handler.operation_mode)
    else:
        organization_name = None
        availability = None
        
    return render(
        request, 'freight/calculator.html', 
        {
            'page_title': 'Reward Calculator',            
            'form': form,             
            'pricing': pricing,
            'price': price,
            'organization_name': organization_name,
            'collateral': collateral * 1000000 if collateral else 0,
            'volume': volume * 1000 if volume else None,
            'expires_on': expires_on,
            'availability': availability,
        }
    )


@login_required
@permission_required('freight.setup_contract_handler')
@token_required(scopes=ContractHandler.get_esi_scopes())
def setup_contract_handler(request, token):
    success = True
    token_char = EveCharacter.objects.get(character_id=token.character_id)

    if ((EveOrganization.get_category_for_operation_mode(FREIGHT_OPERATION_MODE)
        == EveOrganization.CATEGORY_ALLIANCE)
            and token_char.alliance_id is None):
        messages_plus.error(
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
            messages_plus.error(
                request,
                'You can only use your main or alt characters to setup '
                + ' the contract handler. '
                + 'However, character <strong>{}</strong> is neither. '.format(
                    token_char.character_name
                )
            )
            success = False
    
    if success:
        handler = ContractHandler.objects.first()
        if handler and handler.operation_mode != FREIGHT_OPERATION_MODE:
            messages_plus.error(
                request,
                'There already is a contract handler installed for a '
                + 'different operation mode. You need to first delete the '
                + 'existing contract handler in the admin section '
                + 'before you can set up this app for a different operation mode.'
            )
            success = False

    if success:        
        organization, _ = EveOrganization.objects.update_or_create_from_evecharacter(
            token_char,
            EveOrganization.get_category_for_operation_mode(
                FREIGHT_OPERATION_MODE
            )
        )

    if success:
        if handler and handler.organization != organization:
            messages_plus.error(
                request,
                'There already is a contract handler installed for a '
                + 'different organization. You need to first delete the '
                + 'existing contract handler in the admin section '
                + 'before you can set up this app for a different organization.'
            )
            success = False
    
    if success:
        handler, created = ContractHandler.objects.update_or_create(
            organization=organization,
            defaults={
                'character': owned_char,
                'operation_mode': FREIGHT_OPERATION_MODE
            }
        )          
        tasks.run_contracts_sync.delay(            
            force_sync=True,
            user_pk=request.user.pk
        )        
        messages_plus.success(
            request, 
            'Contract Handler setup started for '
            + '<strong>{}</strong> organization '.format(organization.name)
            + 'with <strong>{}</strong> as sync character. '.format(
                    handler.character.character.character_name, 
                )
            + 'Operation mode: <strong>{}</strong>. '.format(handler.operation_mode_friendly)
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
                action_txt = 'Added:' if created else 'Updated:'
                messages_plus.success(
                    request,
                    '{} <strong>{}</strong>'.format(
                        action_txt,                        
                        location.name
                    )
                )
                return redirect('freight:add_location_2')    

            except Exception as ex:
                messages_plus.error(
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

@login_required
@permission_required('freight.view_contracts')
def statistics(request):

    context = {
        'page_title': 'Statistics',
        'max_days': FREIGHT_STATISTICS_MAX_DAYS
    }        
    return render(request, 'freight/statistics.html', context)


@login_required
@permission_required('freight.view_contracts')
def statistics_routes_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = (pytz.utc.localize(datetime.datetime.utcnow()) 
        - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS))
    subfilter = Q(contract__status__exact=Contract.STATUS_FINISHED) & Q(contract__date_accepted__gte=cutoff_date)
    pricing_data = Pricing.objects.select_related() \
        .annotate(contracts=Count('contract', filter=subfilter)) \
        .annotate(rewards=Sum('contract__reward', filter=subfilter)) \
        .annotate(collaterals=Sum('contract__collateral', filter=subfilter)) \
        .annotate(pilots=Count('contract__issuer', distinct=True, filter=subfilter)) \
        .annotate(customers=Count('contract__acceptor', distinct=True, filter=subfilter))

    totals = list()
    for pricing in pricing_data:
        
        if pricing.rewards:
            rewards = pricing.rewards / 1000000
        else:
            rewards = 0

        if pricing.collaterals:
            collaterals = pricing.collaterals / 1000000
        else:
            collaterals = 0
        
        totals.append({
            'name': pricing.name,
            'contracts': '{:,}'.format(pricing.contracts),
            'rewards': '{:,.1f}'.format(rewards),
            'collaterals': '{:,.1f}'.format(collaterals),
            'pilots': '{:,}'.format(pricing.pilots),
            'customers': '{:,}'.format(pricing.customers),
        })

    return JsonResponse(totals, safe=False)


@login_required
@permission_required('freight.view_contracts')
def statistics_pilots_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = (pytz.utc.localize(datetime.datetime.utcnow()) 
        - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS))
    subfilter = Q(contract_acceptor__status__exact=Contract.STATUS_FINISHED) & Q(contract_acceptor__date_accepted__gte=cutoff_date)
    pricing_data = EveCharacter.objects.exclude(contract_acceptor__exact=None).select_related() \
        .annotate(contracts=Count('contract_acceptor', filter=subfilter)) \
        .annotate(rewards=Sum('contract_acceptor__reward', filter=subfilter)) \
        .annotate(collaterals=Sum('contract_acceptor__collateral', filter=subfilter))        

    totals = list()
    for pricing in pricing_data:
        
        if pricing.rewards:
            rewards = pricing.rewards / 1000000
        else:
            rewards = 0

        if pricing.collaterals:
            collaterals = pricing.collaterals / 1000000
        else:
            collaterals = 0
        
        totals.append({
            'name': pricing.character_name,
            'contracts': '{:,}'.format(pricing.contracts),
            'rewards': '{:,.1f}'.format(rewards),
            'collaterals': '{:,.1f}'.format(collaterals),            
        })

    return JsonResponse(totals, safe=False)