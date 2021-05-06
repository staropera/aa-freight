"""scripts generates large amount of moons for load testing

This script can be executed directly from shell.
"""

import os
import sys
from pathlib import Path

myauth_dir = Path(__file__).parent.parent.parent.parent.parent / "myauth"
sys.path.insert(0, str(myauth_dir))

import django  # noqa: E402

# init and setup django project
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myauth.settings.local")
django.setup()

#######################
# main script
import datetime as dt  # noqa: E402
import random  # noqa: E402
from pathlib import Path  # noqa: E402

from django.utils.timezone import now  # noqa: E402

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo  # noqa: E402

from freight.models import Contract, ContractHandler, Location, Pricing  # noqa: E402

MAX_CONTRACTS = 10

print(f"Generating {MAX_CONTRACTS} contracts...")
jita_44, _ = Location.objects.get_or_create(
    id=60003760,
    defaults={
        "name": "Jita IV - Moon 4 - Caldari Navy Assembly Plant",
        "solar_system_id": 30000142,
        "type_id": 52678,
        "category_id": 3,
    },
)
enaluri_5, _ = Location.objects.get_or_create(
    id=60015068,
    defaults={
        "name": "Enaluri V - State Protectorate Assembly Plant",
        "solar_system_id": 30045339,
        "type_id": 1529,
        "category_id": 3,
    },
)
pricing, _ = Pricing.objects.get_or_create(
    start_location=jita_44,
    end_location=enaluri_5,
    defaults={
        "price_base": 200_000_000,
        "days_to_expire": 14,
        "days_to_complete": 3,
        "volume_max": 320_000,
        "details": "GENERATED PRICING FOR TESTING",
    },
)
handler = ContractHandler.objects.first()
acceptor = EveCharacter.objects.all().order_by("?").first()
acceptor_corporation = EveCorporationInfo.objects.get(
    corporation_id=acceptor.corporation_id
)
issuer = EveCharacter.objects.all().order_by("?").first()
issuer_corporation = EveCorporationInfo.objects.get(
    corporation_id=issuer.corporation_id
)
for _ in range(MAX_CONTRACTS):
    contract = Contract.objects.create(
        handler=handler,
        contract_id=random.randint(100_000_000, 200_000_000),
        acceptor=acceptor,
        acceptor_corporation=acceptor_corporation,
        collateral=random.randint(1_000_000_000, 5_000_000_000),
        date_accepted=now() - dt.timedelta(days=2),
        date_completed=now() - dt.timedelta(days=1),
        date_expired=now() + dt.timedelta(days=14),
        date_issued=now() - dt.timedelta(days=3),
        days_to_complete=7,
        end_location=enaluri_5,
        for_corporation=False,
        issuer_corporation=issuer_corporation,
        issuer=issuer,
        reward=random.randint(100_000_000, 500_000_000),
        start_location=jita_44,
        status=random.choice(
            [
                Contract.Status.OUTSTANDING,
                Contract.Status.OUTSTANDING,
                Contract.Status.IN_PROGRESS,
                Contract.Status.FINISHED,
                Contract.Status.FINISHED,
            ]
        ),
        title="GENERATED CONTRACT",
        volume=random.randint(10_000, 300_000),
        pricing=pricing,
    )

print("DONE")
