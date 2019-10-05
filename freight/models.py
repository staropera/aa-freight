import logging
import datetime
from dhooks import Webhook, Embed

from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse

from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter
from allianceauth.authentication.models import CharacterOwnership

from .managers import LocationManager
from evesde.models import EveSolarSystem, EveType
from .app_settings import FREIGHT_DISCORD_WEBHOOK_URL
from .utils import LoggerAddTag, DATETIME_FORMAT


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class Freight(models.Model):

    class Meta:
        managed = False                         
        default_permissions = ()
        permissions = ( 
            ('basic_access', 'Can access this app'),  
            ('setup_contract_handler', 'Can setup contract handler'), 
            ('use_calculator', 'Can use the calculator'), 
            ('view_contracts', 'Can view the contracts list'), 
            ('add_location', 'Can add / update locations'), 
            ('view_statistics', 'Can view freight statistics'), 
        )


class Location(models.Model):    
    CATEGORY_UNKNOWN_ID = 0
    CATEGORY_STATION_ID = 3
    CATEGORY_STRUCTURE_ID = 65
    CATEGORY_CHOICES = [
        (CATEGORY_STATION_ID, 'station'),
        (CATEGORY_STRUCTURE_ID, 'structure'),
        (CATEGORY_UNKNOWN_ID, '(unknown)'),
    ]

    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=100)        
    solar_system_id = models.IntegerField(default=None, null=True, blank=True)
    type_id = models.IntegerField(default=None, null=True, blank=True)
    category_id = models.IntegerField(
        choices=CATEGORY_CHOICES, 
        default=CATEGORY_UNKNOWN_ID
    )
    
    objects = LocationManager()

    @classmethod
    def get_esi_scopes(cls):
        return [         
            'esi-universe.read_structures.v1'
        ]

    def __str__(self):
        return self.name

    @property
    def category(self):
        return self.category_id

    @property
    def solar_system_name(self):        
        return self.name.split(' ', 1)[0]


class Pricing(models.Model):        
    start_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='pricing_start_location'
    )
    end_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='pricing_end_location'
    )    
    active = models.BooleanField(default=True)
    price_base = models.FloatField(default=0, blank=True)
    price_per_volume = models.FloatField(default=0, blank=True)
    price_per_collateral_percent = models.FloatField(default=0, blank=True)
    collateral_min = models.BigIntegerField(default=0, blank=True)
    collateral_max = models.BigIntegerField(default=None, null=True, blank=True)
    volume_max = models.FloatField(default=None, null=True, blank=True)
    days_to_expire = models.IntegerField(default=None, null=True, blank=True)
    days_to_complete = models.IntegerField(default=None, null=True, blank=True)
    details = models.TextField(default=None, null=True, blank=True)

    class Meta:
        unique_together = (('start_location', 'end_location'),)
    
    @property
    def name(self):
        return '{} - {}'.format(
            self.start_location.solar_system_name,
            self.end_location.solar_system_name
        )

    def __str__(self):
        return self.name

    def get_calculated_price(self, volume: float, collateral: float) -> float:
        """returns the calculated price for the given parameters"""
        return (self.price_base
            + volume * self.price_per_volume 
            + collateral  * (self.price_per_collateral_percent / 100))

    def get_contract_pricing_errors(            
            self,
            volume: float,
            collateral: float,
            reward: float = None
        ) -> list:
        """returns list of validation error messages or empty list if ok"""
        errors = list()
        if volume > self.volume_max:            
            errors.append('Exceeds the maximum allowed volume of '
                + '{:,.0f} K m3'.format(self.volume_max / 1000))
        
        if collateral > self.collateral_max:        
            errors.append('Exceeded the maximum allowed collateral of '
                + '{:,.0f} M ISK'.format(self.collateral_max / 1000000))
        
        if collateral < self.collateral_min:
            errors.append('Below the minimum required collateral of '
                + '{:,.0f} M ISK'.format(self.collateral_min / 1000000))

        if reward:
            calculated_price = self.get_calculated_price(
                volume, collateral
            )
            if calculated_price < reward:
                errors.append('Reward is below the calculated price of '
                    + '{:,.0f} M ISK'.format(calculated_price / 1000000))

        return errors
    

class ContractHandler(models.Model):
    alliance = models.OneToOneField(
        EveAllianceInfo, 
        on_delete=models.CASCADE, 
        primary_key=True
    )
    character = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True
    )
    
    version_hash = models.CharField(max_length=32, null=True, default=None, blank=True)    
    last_sync = models.DateTimeField(null=True, default=None, blank=True)


    @classmethod
    def get_esi_scopes(cls):
        return [
            'esi-contracts.read_corporation_contracts.v1',
            'esi-universe.read_structures.v1'
        ]

    def __str__(self):
        return str(self.alliance)


class Contract(models.Model):    
    STATUS_OUTSTANDING = 'outstanding'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_FINISHED_ISSUER = 'finished_issuer'
    STATUS_FINISHED_CONTRACTOR = 'finished_contractor'
    STATUS_FINISHED = 'finished'
    STATUS_CANCELED = 'canceled'
    STATUS_REJECTED = 'rejected'
    STATUS_FAILED = 'failed'
    STATUS_DELETED = 'deleted'
    STATUS_REVERSED = 'reversed'

    STATUS_CHOICES = [
        (STATUS_OUTSTANDING, 'outstanding'),
        (STATUS_IN_PROGRESS, 'in progress'),
        (STATUS_FINISHED_ISSUER, 'finished issuer'),
        (STATUS_FINISHED_CONTRACTOR, 'finished contractor'),
        (STATUS_FINISHED, 'finished'),
        (STATUS_CANCELED, 'canceled'),
        (STATUS_REJECTED, 'rejected'),
        (STATUS_FAILED, 'failed'),
        (STATUS_DELETED, 'deleted'),
        (STATUS_REVERSED, 'reversed'),
    ]

    handler = models.ForeignKey(
        ContractHandler, 
        on_delete=models.CASCADE
    )
    contract_id = models.IntegerField()

    acceptor = models.ForeignKey(
        EveCharacter, 
        on_delete=models.CASCADE, 
        default=None, 
        null=True,
        related_name='contract_acceptor'
    )
    collateral = models.FloatField()    
    date_accepted = models.DateTimeField(default=None, null=True)
    date_completed = models.DateTimeField(default=None, null=True)
    date_expired = models.DateTimeField()
    date_issued = models.DateTimeField()
    days_to_complete = models.IntegerField()
    end_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='contract_end_location'
    )
    for_corporation = models.BooleanField()
    issuer_corporation = models.ForeignKey(
        EveCorporationInfo, 
        on_delete=models.CASCADE,
        related_name='contract_issuer'
    )
    issuer = models.ForeignKey(
        EveCharacter, 
        on_delete=models.CASCADE,        
        related_name='contract_issuer'
    )
    price = models.FloatField()
    reward = models.FloatField()
    start_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='contract_start_location'
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    title = models.CharField(max_length=100, default=None, null=True)    
    volume = models.FloatField()
    date_notified = models.DateTimeField(
        default=None, 
        null=True,
        help_text='datetime of latest notification, None = none has been sent'
    )

    class Meta:
        unique_together = (('handler', 'contract_id'),)
        indexes = [
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return '{}: {} -> {}'.format(
            self.contract_id,
            self.start_location,
            self.end_location
        )

    def get_pricing_errors(self, pricing: Pricing) ->list:
        return pricing.get_contract_pricing_errors(
            self.volume,
            self.collateral,
            self.reward
        )

    def send_notification(self):
        """sends notification about this contract to the DISCORD webhook"""
        if FREIGHT_DISCORD_WEBHOOK_URL:
            avatar_url = 'https://imageserver.eveonline.com/Alliance/{}_128.png'.format(self.handler.alliance.alliance_id)
            logger.info('avatar_url: ' + avatar_url)
            hook = Webhook(
                FREIGHT_DISCORD_WEBHOOK_URL, 
                username='Alliance Freight',
                avatar_url=avatar_url
            )            
            # reverse('freight:contract_list')
            with transaction.atomic():
                logger.info('Trying to sent notification to {}'.format(
                    FREIGHT_DISCORD_WEBHOOK_URL
                ))
                contents = ('There is a new courier contract from {} '.format(
                        self.issuer) + 'looking to be picked up:')

                embed = Embed(
                    timestamp=self.date_issued.isoformat()
                )
                embed.set_thumbnail(self.issuer.portrait_url())
                desc = ''
                desc += '**Route**: {} → {}\n'.format(
                    self.start_location.solar_system_name,
                    self.end_location.solar_system_name
                )                
                desc += '**Reward**: {:,.0f} M ISK\n'.format(
                    self.reward / 1000000
                )
                desc += '**Collateral**: {:,.0f} M ISK\n'.format(
                    self.collateral / 1000000
                )
                desc += '**Volume**: {:,.0f} K m3\n'.format(
                    self.volume / 1000
                )
                """
                desc += '**Price Check**: {}\n'.format(
                    'tbd'
                )
                """
                desc += '**Expires on**: {}\n'.format(
                    self.date_expired.strftime(DATETIME_FORMAT)
                )
                desc += '**Issued by**: {}\n'.format(self.issuer)
                embed.description = desc
                                
                hook.send(content=contents, embed=embed) 
                self.date_notified = datetime.datetime.now(
                    datetime.timezone.utc
                )
                self.save()