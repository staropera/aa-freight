from django.db import models
from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo, EveCharacter
from allianceauth.authentication.models import CharacterOwnership
from evesde.models import EveSolarSystem, EveType, EveItem
from .managers import LocationManager



class Structure(models.Model):    
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(EveCorporationInfo, on_delete=models.CASCADE)
    position_x = models.FloatField()
    position_y = models.FloatField()
    position_z = models.FloatField()
    solar_system = models.ForeignKey(EveSolarSystem, on_delete=models.CASCADE)
    type = models.ForeignKey(EveType, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Location(models.Model):
    id = models.BigIntegerField(primary_key=True)
    item = models.OneToOneField(
        EveItem, 
        on_delete=models.SET_DEFAULT, 
        default=None, 
        null=True
    )
    structure = models.OneToOneField(
        Structure, 
        on_delete=models.SET_DEFAULT, 
        default=None, 
        null=True
    )
    objects = LocationManager()

    @property
    def name(self):
        if self.item:
            return self.item.eveitemdenormalized.item_name
        elif self.structure:
            return self.structure.name
        else:
            return 'Unknown location:{}'.format(self.id)

    def __str__(self):
        return self.name


class JfService(models.Model):
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
    
    version_hash = models.CharField(max_length=32, null=True, default=None)    
    last_sync = models.DateTimeField(null=True, default=None)

    class Meta:
        permissions = (
            ('access_jfservice', 'Can access the JF Service'),
        )

    @classmethod
    def get_esi_scopes(cls):
        return [
            'esi-contracts.read_corporation_contracts.v1',
            'esi-universe.read_structures.v1'
        ]

    def __str__(self):
        return str(self.alliance)


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
    active = models.BooleanField()
    price_per_volume = models.FloatField(default=None, null=True)
    price_collateral_percent = models.FloatField(default=None, null=True)    
    collateral_max = models.BigIntegerField(default=None, null=True)
    price_base = models.FloatField(default=None, null=True)
    volume_max = models.FloatField(default=None, null=True)
    pricing_comment = models.TextField(default=None, null=True)

    class Meta:
        unique_together = (('start_location', 'end_location'),)
    
    def __str__(self):
        return '{} -> {}'.format(            
            self.start_location,
            self.end_location
        )


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

    jfservice = models.ForeignKey(
        JfService, 
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

    class Meta:
        unique_together = (('jfservice', 'contract_id'),)
        indexes = [
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return '{}: {} -> {}'.format(
            self.contract_id,
            self.start_location,
            self.end_location
        )
