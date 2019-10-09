import datetime
import logging

from .discordhook import Webhook, Embed

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo
from allianceauth.eveonline.models import EveCharacter
from evesde.models import EveSolarSystem, EveType

from .app_settings import FREIGHT_DISCORD_WEBHOOK_URL, FREIGHT_DISCORD_AVATAR_URL
from .managers import LocationManager, ContractManager
from .utils import LoggerAddTag, DATETIME_FORMAT


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class Freight(models.Model):
    """Meta model for global app permissions"""

    class Meta:
        managed = False                         
        default_permissions = ()
        permissions = ( 
            ('add_location', 'Can add / update locations'), 
            ('basic_access', 'Can access this app'),              
            ('setup_contract_handler', 'Can setup contract handler'), 
            ('use_calculator', 'Can use the calculator'), 
            ('view_contracts', 'Can view the contracts list'),             
            ('view_statistics', 'Can view freight statistics'), 
        )


class Location(models.Model):
    """An Eve Online courier contract location: station or Upwell structure""" 
    CATEGORY_UNKNOWN_ID = 0
    CATEGORY_STATION_ID = 3
    CATEGORY_STRUCTURE_ID = 65
    CATEGORY_CHOICES = [
        (CATEGORY_STATION_ID, 'station'),
        (CATEGORY_STRUCTURE_ID, 'structure'),
        (CATEGORY_UNKNOWN_ID, '(unknown)'),
    ]

    id = models.BigIntegerField(
        primary_key=True,
        validators=[MinValueValidator(0)],
        help_text='Eve Online location ID, ' \
            + 'either item ID for stations or structure ID for structures'
    )
    name = models.CharField(
        max_length=100,
        help_text='In-game name of this station or structure'
    ) 
    solar_system_id = models.IntegerField(
        default=None, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Eve Online solar system ID'
    )
    type_id = models.IntegerField(
        default=None, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Eve Online type ID'
    )
    category_id = models.IntegerField(
        choices=CATEGORY_CHOICES, 
        default=CATEGORY_UNKNOWN_ID,
        validators=[MinValueValidator(0)],
        help_text='Eve Online category ID'
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
    """Pricing for a courier route"""
    start_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='pricing_start_location', 
        help_text='Starting station or structure for courier route'
    )
    end_location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE,
        related_name='pricing_end_location', 
        help_text='Destination station or structure for courier route'
    )    
    active = models.BooleanField(
        default=True, 
        help_text='Non active pricings will not be used or shown'
    )
    price_base = models.FloatField(
        default=None, 
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Base price in ISK'
    )
    price_min = models.FloatField(
        default=None, 
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Minimum total price in ISK'
    )
    price_per_volume = models.FloatField(
        default=None, 
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Add-on price per m3 volume in ISK'
    )
    price_per_collateral_percent = models.FloatField(
        default=None, 
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Add-on price in % of collateral'
    )
    collateral_min = models.BigIntegerField(
        default=None, 
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Minimum required collateral in ISK'
    )
    collateral_max = models.BigIntegerField(
        default=None, 
        null=True, 
        blank=True, 
        validators=[MinValueValidator(0)],
        help_text='Maximum allowed collateral in ISK'
    )
    volume_min = models.FloatField(
        default=None, 
        null=True, 
        blank=True, 
        validators=[MinValueValidator(0)],
        help_text='Minimum allowed volume in m3'
    )
    volume_max = models.FloatField(
        default=None, 
        null=True, 
        blank=True, 
        validators=[MinValueValidator(0)],
        help_text='Maximum allowed volume in m3'
    )
    days_to_expire = models.IntegerField(
        default=None, 
        null=True, 
        blank=True, 
        validators=[MinValueValidator(1)],
        help_text='Recommended days for contracts to expire'
    )
    days_to_complete = models.IntegerField(
        default=None, 
        null=True, 
        blank=True, 
        validators=[MinValueValidator(1)],
        help_text='Recommended days for contract completion'
    )
    details = models.TextField(
        default=None, 
        null=True, 
        blank=True, 
        help_text='Text with additional instructions for using this pricing'
    )

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

    def clean(self):
        if not (self.price_base 
                or self.price_min 
                or self.price_per_volume 
                or self.price_per_collateral_percent):
            raise ValidationError(
                'You must specify at least one price component'
            )

    def get_calculated_price(self, volume: float, collateral: float) -> float:
        """returns the calculated price for the given parameters"""

        if volume < 0:
            raise ValueError('volume can not be negative')
        if collateral < 0:
            raise ValueError('collateral can not be negative')
        
        self.clean()

        price_base = 0 if not self.price_base else self.price_base
        price_min = 0 if not self.price_min else self.price_min
        price_per_volume = 0 \
            if not self.price_per_volume else self.price_per_volume
        price_per_collateral_percent = 0 \
            if not self.price_per_collateral_percent \
            else self.price_per_collateral_percent

        return max(price_min, (price_base
            + volume * price_per_volume
            + collateral  * (price_per_collateral_percent / 100)))

    def get_contract_price_check_issues(            
            self,
            volume: float,
            collateral: float,
            reward: float = None
        ) -> list:
        """returns list of validation error messages or none if ok"""
        
        if volume < 0:
            raise ValueError('volume can not be negative')
        if collateral < 0:
            raise ValueError('collateral can not be negative')
        if reward and reward < 0:
            raise ValueError('reward can not be negative')
        
        self.clean()
        
        issues = list()
        if self.volume_min and volume < self.volume_min:
            issues.append('below the minimum required volume of '
                + '{:,.0f} K m3'.format(self.volume_min / 1000))
                
        if self.volume_max and volume > self.volume_max:
            issues.append('exceeds the maximum allowed volume of '
                + '{:,.0f} K m3'.format(self.volume_max / 1000))
        
        if self.collateral_max and collateral > self.collateral_max:
            issues.append('exceeds the maximum allowed collateral of '
                + '{:,.0f} M ISK'.format(self.collateral_max / 1000000))
        
        if self.collateral_min and collateral < self.collateral_min:
            issues.append('below the minimum required collateral of '
                + '{:,.0f} M ISK'.format(self.collateral_min / 1000000))

        if reward:
            calculated_price = self.get_calculated_price(
                volume, collateral
            )
            if reward < calculated_price:
                issues.append('reward is below the calculated price of '
                    + '{:,.0f} M ISK'.format(calculated_price / 1000000))

        if len(issues) == 0:
            return None
        else:
            return issues
    

class ContractHandler(models.Model):
    """Handler for syncing of contracts belonging to an alliance"""

    ERROR_NONE = 0
    ERROR_TOKEN_INVALID = 1
    ERROR_TOKEN_EXPIRED = 2
    ERROR_INSUFFICIENT_PERMISSIONS = 3    
    ERROR_NO_CHARACTER = 4
    ERROR_ESI_UNAVAILABLE = 5
    ERROR_UNKNOWN = 99

    ERRORS_LIST = [
        (ERROR_NONE, 'No error'),
        (ERROR_TOKEN_INVALID, 'Invalid token'),
        (ERROR_TOKEN_EXPIRED, 'Expired token'),
        (ERROR_INSUFFICIENT_PERMISSIONS, 'Insufficient permissions'),
        (ERROR_NO_CHARACTER, 'No character set for fetching alliance contacts'),
        (ERROR_ESI_UNAVAILABLE, 'ESI API is currently unavailable'),
        (ERROR_UNKNOWN, 'Unknown error'),
    ]

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
    version_hash = models.CharField(
        max_length=32, 
        null=True, 
        default=None, 
        blank=True,
        help_text='hash to identify changes to contracts'
    )
    last_sync = models.DateTimeField(
        null=True, 
        default=None, 
        blank=True,
        help_text='when the last sync happened'
    )
    last_error = models.IntegerField(
        choices=ERRORS_LIST, 
        default=ERROR_NONE,
        help_text='error that occurred at the last sync atttempt (if any)'
    )

    @classmethod
    def get_esi_scopes(cls):
        return [
            'esi-contracts.read_corporation_contracts.v1',
            'esi-universe.read_structures.v1'
        ]

    def __str__(self):
        return str(self.alliance)

    def get_last_error_message(self):
        msg = [(x, y) for x, y in self.ERRORS_LIST if x == self.last_error]
        return msg[0][1] if len(msg) > 0 else 'Undefined error'


class Contract(models.Model): 
    """An Eve Online courier contract with additional meta data"""
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
    pricing = models.ForeignKey(
        Pricing, 
        on_delete=models.SET_DEFAULT, 
        default=None, 
        null=True
    )
    date_notified = models.DateTimeField(
        default=None, 
        null=True,
        help_text='datetime of latest notification, None = none has been sent'
    )
    issues = models.TextField(
        default=None,
        null=True,
        help_text='List or price check issues as JSON array of strings or None'
    )

    objects = ContractManager()

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

    def get_price_check_issues(self, pricing: Pricing) -> list:
        return pricing.get_contract_price_check_issues(
            self.volume,
            self.collateral,
            self.reward
        )

    def send_notification(self):
        """sends notification about this contract to the DISCORD webhook"""
        if FREIGHT_DISCORD_WEBHOOK_URL:                        
            if FREIGHT_DISCORD_AVATAR_URL:
                avatar_url = FREIGHT_DISCORD_AVATAR_URL
            else:    
                avatar_url = ('https://imageserver.eveonline.com/Alliance/'
                    + '{}_128.png'.format(self.handler.alliance.alliance_id))
            hook = Webhook(
                FREIGHT_DISCORD_WEBHOOK_URL, 
                username='Alliance Freight',
                avatar_url=avatar_url
            )            
            # reverse('freight:contract_list')
            with transaction.atomic():
                logger.info(
                    'Trying to sent notification about contract {}'.format(
                        self.contract_id
                    ) + ' to {}'.format(FREIGHT_DISCORD_WEBHOOK_URL))
                contents = ('There is a new courier contract from {} '.format(
                        self.issuer) + 'looking to be picked up:')
               
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
                if self.pricing:
                    issues = self.get_price_check_issues(self.pricing)
                    if not issues:                        
                        check_text = 'passed'
                        color = 0x008000
                    else:
                        check_text = 'FAILED'
                        color = 0xFF0000
                else:
                    check_text = 'N/A'
                    color = None
                desc += '**Price Check**: {}\n'.format(check_text)
                desc += '**Expires on**: {}\n'.format(
                    self.date_expired.strftime(DATETIME_FORMAT)
                )
                desc += '**Issued by**: {}\n'.format(self.issuer)
                
                embed = Embed(
                    description=desc,
                    timestamp=self.date_issued,
                    color=color,
                    thumbnail_url=self.issuer.portrait_url()
                )                
                                                
                hook.send(content=contents, embeds=[embed]) 
                self.date_notified = datetime.datetime.now(
                    datetime.timezone.utc
                )
                self.save()