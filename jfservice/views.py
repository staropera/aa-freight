import math
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404
from django.template import loader
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from allianceauth.authentication.models import CharacterOwnership
from esi.decorators import token_required
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter
from .models import *
from . import tasks
from .forms import CalculatorForm

@login_required
@permission_required('jfservice.access_jfservice')
def index(request):
    
    contracts = Contract.objects.filter(
        handler__alliance__alliance_id=request.user.profile.main_character.alliance_id,
        status__in=[
            Contract.STATUS_OUTSTANDING,
            Contract.STATUS_IN_PROGRESS
        ]
    )
    
    context = {
        'contracts': contracts
    }        
    return render(request, 'jfservice/contracts.html', context)


@login_required
@permission_required('jfservice.access_jfservice')
def calculator(request):            
    
    
    if request.method != 'POST':
        form = CalculatorForm()
        price = None

    else:
        form = CalculatorForm(request.POST)
        if form.is_valid():
            pricing = form.cleaned_data['pricing']            
            price = math.ceil((pricing.price_base 
                + form.cleaned_data['volume'] * 1000 * pricing.price_per_volume 
                + form.cleaned_data['collateral'] * 1000000 * (pricing.price_collateral_percent / 100)
            ) / 1000000) * 1000000
        else:
            price = None
        
    return render(
        request, 'jfservice/calculator.html', 
        {
            'form': form, 
            'price': price
        }
    )

    

@login_required
@permission_required('jfservice.access_jfservice')
@token_required(scopes=ContractsHandler.get_esi_scopes())
def create_or_update_service(request, token):
    success = True
    token_char = EveCharacter.objects.get(character_id=token.character_id)

    if token_char.alliance_id is None:
        messages.warning(
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
            messages.warning(
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
        messages.success(
            request, 
            'JF service created for {} alliance with {} as sync character. '.format(                    
                    alliance.alliance_name,
                    contracts_handler.character.character.character_name, 
                )
            + 'Started syncing of courier contracts. '
            + 'You will receive a report once it is completed.'
        )
    return redirect('jfservice:index')

"""
def form_handle(request):
    form = MyForm()
    if request.method=='POST':
        form = MyForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            #now in the object cd, you have the form as a dictionary.
            a = cd.get('a')

    #blah blah encode parameters for a url blah blah 
    #and make another post request
    #edit : added ": "  after    if request.method=='POST'

"""