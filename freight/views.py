import datetime
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.forms import HiddenInput
from django.http import JsonResponse
from django.db.models import Count, Sum, Q
from django.shortcuts import render, redirect
from django.utils.html import mark_safe
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo, EveCharacter

from esi.decorators import token_required
from esi.models import Token

from . import tasks
from .app_settings import (
    FREIGHT_APP_NAME,
    FREIGHT_STATISTICS_MAX_DAYS,
    FREIGHT_OPERATION_MODE,
)
from .models import Contract, ContractHandler, EveEntity, Location, Pricing
from .utils import DATETIME_FORMAT, messages_plus, LoggerAddTag, create_bs_glyph_2_html


logger = LoggerAddTag(logging.getLogger(__name__), __package__)

ADD_LOCATION_TOKEN_TAG = "freight_add_location_token"
CONTRACT_LIST_USER = "user"
CONTRACT_LIST_ACTIVE = "active"


@login_required
@permission_required("freight.basic_access")
def index(request):
    return redirect("freight:calculator")


@login_required
@permission_required("freight.view_contracts")
def contract_list_active(request):

    context = {
        "app_title": FREIGHT_APP_NAME,
        "page_title": "Active Contracts",
        "category": CONTRACT_LIST_ACTIVE,
    }
    return render(request, "freight/contract_list.html", context)


@login_required
@permission_required("freight.use_calculator")
def contract_list_user(request):

    context = {
        "app_title": FREIGHT_APP_NAME,
        "page_title": "My Contracts",
        "category": CONTRACT_LIST_USER,
    }
    return render(request, "freight/contract_list.html", context)


@login_required
@permission_required("freight.basic_access")
def contract_list_data(request, category):
    """returns list of outstanding contracts for contract_list AJAX call"""

    def datetime_format(x):
        return x.strftime(DATETIME_FORMAT) if x else None

    def character_format(x):
        return x.character_name if x else None

    contracts = _get_contracts_for_contract_list(category, request)

    contracts_data = list()
    for contract in contracts:
        if contract.has_pricing:
            route_name = contract.pricing.name
            if not contract.has_pricing_errors:
                glyph = "ok"
                color = "green"
                tooltip_text = route_name
            else:
                glyph = "warning-sign"
                color = "red"
                tooltip_text = "{}\n{}".format(
                    route_name, "\n".join(contract.get_issue_list())
                )
            pricing_check = create_bs_glyph_2_html(glyph, tooltip_text, color)
        else:
            route_name = ""
            pricing_check = "-"

        if contract.title:
            notes = create_bs_glyph_2_html("envelope", contract.title)
        else:
            notes = ""

        if settings.DEBUG:
            notes += " {}".format(contract.contract_id)

        contracts_data.append(
            {
                "contract_id": contract.contract_id,
                "status": contract.status,
                "start_location": str(contract.start_location),
                "end_location": str(contract.end_location),
                "reward": "{:,.0f}".format(contract.reward / 1000000),
                "collateral": "{:,.0f}".format(contract.collateral / 1000000),
                "volume": "{:,.0f}".format(contract.volume / 1000),
                "date_issued": datetime_format(contract.date_issued),
                "date_expired": datetime_format(contract.date_expired),
                "issuer": character_format(contract.issuer),
                "notes": notes,
                "date_accepted": datetime_format(contract.date_accepted),
                "acceptor": contract.acceptor_name,
                "has_pricing": contract.has_pricing,
                "has_pricing_errors": contract.has_pricing_errors,
                "pricing_check": pricing_check,
                "route_name": route_name,
                "is_in_progress": contract.is_in_progress,
                "is_failed": contract.is_failed,
                "is_completed": contract.is_completed,
            }
        )

    return JsonResponse(contracts_data, safe=False)


def _get_contracts_for_contract_list(category, request):
    if category == CONTRACT_LIST_ACTIVE:
        if not request.user.has_perm("freight.view_contracts"):
            raise RuntimeError("Insufficient permissions")

        else:
            contracts = (
                Contract.objects.filter(
                    status__in=[
                        Contract.STATUS_OUTSTANDING,
                        Contract.STATUS_IN_PROGRESS,
                    ]
                )
                .exclude(date_expired__lt=now())
                .select_related()
            )

    elif category == CONTRACT_LIST_USER:
        if not request.user.has_perm("freight.use_calculator"):
            raise RuntimeError("Insufficient permissions")

        else:
            user_characters = [
                x.character
                for x in request.user.character_ownerships.select_related().all()
            ]
            contracts = (
                Contract.objects.filter(issuer__in=user_characters)
                .filter(
                    status__in=[
                        Contract.STATUS_OUTSTANDING,
                        Contract.STATUS_IN_PROGRESS,
                        Contract.STATUS_FINISHED,
                        Contract.STATUS_FAILED,
                    ]
                )
                .select_related()
            )

    else:
        raise ValueError("Invalid category: {}".format(category))

    return contracts


@login_required
@permission_required("freight.use_calculator")
def calculator(request, pricing_pk=None):
    from .forms import CalculatorForm

    if request.method != "POST":
        pricing = Pricing.objects.get_or_default(pricing_pk)
        form = CalculatorForm(initial={"pricing": pricing})
        price = None

    else:
        form = CalculatorForm(request.POST)
        request.POST._mutable = True
        pricing = Pricing.objects.get_or_default(form.data["pricing"])
        volume, collateral, price = form.get_calculated_data(pricing)

    if pricing:
        price_per_volume_eff = pricing.price_per_volume_eff()
        if not pricing.requires_volume():
            form.fields["volume"].widget = HiddenInput()
        if not pricing.requires_collateral():
            form.fields["collateral"].widget = HiddenInput()
    else:
        price_per_volume_eff = None

    if price:
        if pricing.days_to_expire:
            expires_on = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(days=pricing.days_to_expire)
        else:
            expires_on = None
    else:
        collateral = None
        volume = None
        expires_on = None

    handler = ContractHandler.objects.first()
    if handler:
        organization_name = handler.organization.name
        availability = handler.get_availability_text_for_contracts()
    else:
        organization_name = None
        availability = None

    return render(
        request,
        "freight/calculator.html",
        {
            "app_title": FREIGHT_APP_NAME,
            "page_title": "Reward Calculator",
            "form": form,
            "pricing": pricing,
            "price": price,
            "organization_name": organization_name,
            "collateral": collateral if collateral is not None else 0,
            "volume": volume if volume is not None else None,
            "expires_on": expires_on,
            "availability": availability,
            "pricing_price_per_volume_eff": price_per_volume_eff,
        },
    )


@login_required
@permission_required("freight.setup_contract_handler")
@token_required(scopes=ContractHandler.get_esi_scopes())
def setup_contract_handler(request, token):
    success = True
    token_char = EveCharacter.objects.get(character_id=token.character_id)

    if (
        EveEntity.get_category_for_operation_mode(FREIGHT_OPERATION_MODE)
        == EveEntity.CATEGORY_ALLIANCE
    ) and token_char.alliance_id is None:
        messages_plus.error(
            request,
            "Can not setup contract handler, "
            "because {} is not a member of any alliance".format(token_char),
        )
        success = False

    if success:
        try:
            owned_char = CharacterOwnership.objects.get(
                user=request.user, character=token_char
            )
        except CharacterOwnership.DoesNotExist:
            messages_plus.error(
                request,
                mark_safe(
                    "You can only use your main or alt characters to setup "
                    " the contract handler. "
                    "However, character <strong>{}</strong> is neither. ".format(
                        token_char.character_name
                    )
                ),
            )
            success = False

    if success:
        handler = ContractHandler.objects.first()
        if handler and handler.operation_mode != FREIGHT_OPERATION_MODE:
            messages_plus.error(
                request,
                "There already is a contract handler installed for a "
                "different operation mode. You need to first delete the "
                "existing contract handler in the admin section "
                "before you can set up this app for a different operation mode.",
            )
            success = False

    if success:
        organization, _ = EveEntity.objects.update_or_create_from_evecharacter(
            token_char,
            EveEntity.get_category_for_operation_mode(FREIGHT_OPERATION_MODE),
        )

        handler, _ = ContractHandler.objects.update_or_create(
            organization=organization,
            defaults={
                "character": owned_char,
                "operation_mode": FREIGHT_OPERATION_MODE,
            },
        )
        tasks.run_contracts_sync.delay(force_sync=True, user_pk=request.user.pk)
        messages_plus.success(
            request,
            mark_safe(
                "Contract Handler setup started for "
                "<strong>{}</strong> organization "
                "with <strong>{}</strong> as sync character. "
                "Operation mode: <strong>{}</strong>. "
                "Started syncing of courier contracts. "
                "You will receive a report once it is completed.".format(
                    organization.name,
                    handler.character.character.character_name,
                    handler.operation_mode_friendly,
                )
            ),
        )

    return redirect("freight:index")


@login_required
@token_required(scopes=Location.get_esi_scopes())
@permission_required("freight.add_location")
def add_location(request, token):
    request.session[ADD_LOCATION_TOKEN_TAG] = token.pk
    return redirect("freight:add_location_2")


@login_required
@permission_required("freight.add_location")
def add_location_2(request):
    from .forms import AddLocationForm

    if ADD_LOCATION_TOKEN_TAG not in request.session:
        raise RuntimeError("Missing token in session")
    else:
        token = Token.objects.get(pk=request.session[ADD_LOCATION_TOKEN_TAG])

    if request.method != "POST":
        form = AddLocationForm()

    else:
        form = AddLocationForm(request.POST)
        if form.is_valid():
            location_id = form.cleaned_data["location_id"]
            try:
                location, created = Location.objects.update_or_create_from_esi(
                    token=token, location_id=location_id, add_unknown=False
                )
                action_txt = "Added:" if created else "Updated:"
                messages_plus.success(
                    request,
                    mark_safe(
                        "{} <strong>{}</strong>".format(action_txt, location.name)
                    ),
                )
                return redirect("freight:add_location_2")

            except Exception as ex:
                messages_plus.error(
                    request,
                    "Failed to add location with token from {} "
                    "for location ID {}: {}".format(
                        token.character_name, location_id, type(ex).__name__
                    ),
                )

    return render(
        request,
        "freight/add_location.html",
        {
            "app_title": FREIGHT_APP_NAME,
            "page_title": "Add / Update Location",
            "form": form,
            "token_char_name": token.character_name,
        },
    )


@login_required
@permission_required("freight.view_statistics")
def statistics(request):

    context = {
        "app_title": FREIGHT_APP_NAME,
        "page_title": "Statistics",
        "max_days": FREIGHT_STATISTICS_MAX_DAYS,
    }
    return render(request, "freight/statistics.html", context)


@login_required
@permission_required("freight.view_statistics")
def statistics_routes_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = now() - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS)
    finished_contracts = Q(contract__status__exact=Contract.STATUS_FINISHED) & Q(
        contract__date_completed__gte=cutoff_date
    )
    route_totals = (
        Pricing.objects.select_related()
        .annotate(contracts_count=Count("contract", filter=finished_contracts))
        .annotate(rewards=Sum("contract__reward", filter=finished_contracts))
        .annotate(collaterals=Sum("contract__collateral", filter=finished_contracts))
        .annotate(
            pilots=Count("contract__acceptor", distinct=True, filter=finished_contracts)
        )
        .annotate(
            customers=Count(
                "contract__issuer", distinct=True, filter=finished_contracts
            )
        )
    )

    totals = list()
    for route in route_totals:
        if route.contracts_count > 0:
            if route.rewards:
                rewards = route.rewards / 1000000
            else:
                rewards = 0

            if route.collaterals:
                collaterals = route.collaterals / 1000000
            else:
                collaterals = 0

            totals.append(
                {
                    "name": route.name,
                    "contracts": "{:,}".format(route.contracts_count),
                    "rewards": "{:,.0f}".format(rewards),
                    "collaterals": "{:,.0f}".format(collaterals),
                    "pilots": "{:,}".format(route.pilots),
                    "customers": "{:,}".format(route.customers),
                }
            )

    return JsonResponse(totals, safe=False)


@login_required
@permission_required("freight.view_statistics")
def statistics_pilots_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = now() - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS)

    finished_contracts = Q(
        contract_acceptor__status__exact=Contract.STATUS_FINISHED
    ) & Q(contract_acceptor__date_completed__gte=cutoff_date)

    pilot_totals = (
        EveCharacter.objects.exclude(contract_acceptor__exact=None)
        .select_related()
        .annotate(contracts_count=Count("contract_acceptor", filter=finished_contracts))
        .annotate(rewards=Sum("contract_acceptor__reward", filter=finished_contracts))
        .annotate(
            collaterals=Sum("contract_acceptor__collateral", filter=finished_contracts)
        )
    )

    totals = list()
    for pilot in pilot_totals:
        if pilot.contracts_count > 0:
            if pilot.rewards:
                rewards = pilot.rewards / 1000000
            else:
                rewards = 0

            if pilot.collaterals:
                collaterals = pilot.collaterals / 1000000
            else:
                collaterals = 0

            totals.append(
                {
                    "name": pilot.character_name,
                    "corporation": pilot.corporation_name,
                    "contracts": "{:,}".format(pilot.contracts_count),
                    "rewards": "{:,.0f}".format(rewards),
                    "collaterals": "{:,.0f}".format(collaterals),
                }
            )

    return JsonResponse(totals, safe=False)


@login_required
@permission_required("freight.view_statistics")
def statistics_pilot_corporations_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = now() - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS)

    finished_contracts = Q(
        contract_acceptor_corporation__status__exact=Contract.STATUS_FINISHED
    ) & Q(contract_acceptor_corporation__date_completed__gte=cutoff_date)

    corporation_totals = (
        EveCorporationInfo.objects.exclude(contract_acceptor_corporation__exact=None)
        .select_related()
        .annotate(
            contracts_count=Count(
                "contract_acceptor_corporation", filter=finished_contracts
            )
        )
        .annotate(
            rewards=Sum(
                "contract_acceptor_corporation__reward", filter=finished_contracts
            )
        )
        .annotate(
            collaterals=Sum(
                "contract_acceptor_corporation__collateral", filter=finished_contracts
            )
        )
    )

    totals = list()
    for corporation in corporation_totals:
        if corporation.contracts_count > 0:
            if corporation.rewards:
                rewards = corporation.rewards / 1000000
            else:
                rewards = 0

            if corporation.collaterals:
                collaterals = corporation.collaterals / 1000000
            else:
                collaterals = 0

            totals.append(
                {
                    "name": corporation.corporation_name,
                    "alliance": corporation.alliance.alliance_name
                    if corporation.alliance
                    else "",
                    "contracts": "{:,}".format(corporation.contracts_count),
                    "rewards": "{:,.0f}".format(rewards),
                    "collaterals": "{:,.0f}".format(collaterals),
                }
            )

    return JsonResponse(totals, safe=False)


@login_required
@permission_required("freight.view_statistics")
def statistics_customer_data(request):
    """returns totals for statistics as JSON"""

    cutoff_date = now() - datetime.timedelta(FREIGHT_STATISTICS_MAX_DAYS)
    finished_contracts = Q(contract_issuer__status__exact=Contract.STATUS_FINISHED) & Q(
        contract_issuer__date_completed__gte=cutoff_date
    )
    customer_totals = (
        EveCharacter.objects.exclude(contract_issuer__exact=None)
        .select_related()
        .annotate(contracts_count=Count("contract_issuer", filter=finished_contracts))
        .annotate(rewards=Sum("contract_issuer__reward", filter=finished_contracts))
        .annotate(
            collaterals=Sum("contract_issuer__collateral", filter=finished_contracts)
        )
    )

    totals = list()
    for customer in customer_totals:
        if customer.contracts_count > 0:
            if customer.rewards:
                rewards = customer.rewards / 1000000
            else:
                rewards = 0

            if customer.collaterals:
                collaterals = customer.collaterals / 1000000
            else:
                collaterals = 0

            totals.append(
                {
                    "name": customer.character_name,
                    "corporation": customer.corporation_name,
                    "contracts": "{:,}".format(customer.contracts_count),
                    "rewards": "{:,.0f}".format(rewards),
                    "collaterals": "{:,.0f}".format(collaterals),
                }
            )

    return JsonResponse(totals, safe=False)
