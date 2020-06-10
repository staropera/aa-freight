import json
from datetime import timedelta
import hashlib
import logging
from urllib.parse import urljoin

from dhooks_lite import Webhook, Embed, Thumbnail

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership, User
from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from allianceauth.notifications import notify
from allianceauth.services.modules.discord.models import DiscordUser

from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token

from .app_settings import (
    FREIGHT_APP_NAME,
    FREIGHT_FULL_ROUTE_NAMES,
    FREIGHT_HOURS_UNTIL_STALE_STATUS,
    FREIGHT_DISCORD_WEBHOOK_URL,
    FREIGHT_DISCORD_DISABLE_BRANDING,
    FREIGHT_DISCORD_MENTIONS,
    FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL,
    FREIGHT_CONTRACT_SYNC_GRACE_MINUTES,
    FREIGHT_OPERATION_MODE,
    FREIGHT_OPERATION_MODES,
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_MY_CORPORATION,
    FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE,
    FREIGHT_OPERATION_MODE_CORP_PUBLIC,
)
from .managers import ContractManager, EveEntityManager, LocationManager, PricingManager
from .helpers.esi_fetch import esi_fetch
from .utils import (
    app_labels,
    DATETIME_FORMAT,
    get_site_base_url,
    LoggerAddTag,
    make_logger_prefix,
)


logger = LoggerAddTag(logging.getLogger(__name__), __package__)


class Freight(models.Model):
    """Meta model for global app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("add_location", "Can add / update locations"),
            ("basic_access", "Can access this app"),
            ("setup_contract_handler", "Can setup contract handler"),
            ("use_calculator", "Can use the calculator"),
            ("view_contracts", "Can view the contracts list"),
            ("view_statistics", "Can view freight statistics"),
        )


class Location(models.Model):
    """An Eve Online courier contract location: station or Upwell structure"""

    CATEGORY_UNKNOWN_ID = 0
    CATEGORY_STATION_ID = 3
    CATEGORY_STRUCTURE_ID = 65
    CATEGORY_CHOICES = [
        (CATEGORY_STATION_ID, "station"),
        (CATEGORY_STRUCTURE_ID, "structure"),
        (CATEGORY_UNKNOWN_ID, "(unknown)"),
    ]

    id = models.BigIntegerField(
        primary_key=True,
        validators=[MinValueValidator(0)],
        help_text="Eve Online location ID, "
        "either item ID for stations or structure ID for structures",
    )
    name = models.CharField(
        max_length=100, help_text="In-game name of this station or structure"
    )
    solar_system_id = models.PositiveIntegerField(
        default=None, null=True, blank=True, help_text="Eve Online solar system ID"
    )
    type_id = models.PositiveIntegerField(
        default=None, null=True, blank=True, help_text="Eve Online type ID"
    )
    category_id = models.PositiveIntegerField(
        choices=CATEGORY_CHOICES,
        default=CATEGORY_UNKNOWN_ID,
        help_text="Eve Online category ID",
    )

    objects = LocationManager()

    @classmethod
    def get_esi_scopes(cls):
        return ["esi-universe.read_structures.v1"]

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return "{}(pk={}, name='{}')".format(
            self.__class__.__name__, self.pk, self.name
        )

    @property
    def category(self):
        return self.category_id

    @property
    def solar_system_name(self):
        return self.name.split(" ", 1)[0]

    @property
    def location_name(self):
        return self.name.rsplit("-", 1)[1].strip()


class Pricing(models.Model):
    """Pricing for a courier route"""

    start_location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="pricing_start_location",
        help_text="Starting station or structure for courier route",
    )
    end_location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="pricing_end_location",
        help_text="Destination station or structure for courier route",
    )
    is_bidirectional = models.BooleanField(
        default=True,
        help_text="Whether this pricing is valid for contracts "
        "in either direction or only the one specified",
    )
    price_base = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Base price in ISK",
    )
    price_min = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Minimum total price in ISK",
    )
    price_per_volume = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Add-on price per m3 volume in ISK",
    )
    use_price_per_volume_modifier = models.BooleanField(
        default=False, help_text="Whether the global price per volume modifier is used"
    )
    price_per_collateral_percent = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Add-on price in % of collateral",
    )
    collateral_min = models.BigIntegerField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Minimum required collateral in ISK",
    )
    collateral_max = models.BigIntegerField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Maximum allowed collateral in ISK",
    )
    volume_min = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Minimum allowed volume in m3",
    )
    volume_max = models.FloatField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Maximum allowed volume in m3",
    )
    days_to_expire = models.PositiveIntegerField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Recommended days for contracts to expire",
    )
    days_to_complete = models.PositiveIntegerField(
        default=None,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Recommended days for contract completion",
    )
    details = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="Text with additional instructions for using this pricing",
    )
    is_active = models.BooleanField(
        default=True, help_text="Non active pricings will not be used or shown"
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "The default pricing will be preselected in the calculator. "
            "Please make sure to only mark one pricing as default."
        ),
    )

    objects = PricingManager()

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return "{}(pk={}, name='{}')".format(
            self.__class__.__name__, self.pk, self.name_full
        )

    class Meta:
        unique_together = (("start_location", "end_location"),)

    @property
    def name(self) -> str:
        return self._name(FREIGHT_FULL_ROUTE_NAMES)

    @property
    def name_full(self) -> str:
        return self._name(full_name=True)

    @property
    def name_short(self) -> str:
        return self._name(full_name=False)

    def _name(self, full_name: bool) -> str:
        if full_name:
            start_name = self.start_location.name
            end_name = self.end_location.name
        else:
            start_name = self.start_location.solar_system_name
            end_name = self.end_location.solar_system_name

        route_name = "{} {} {}".format(
            start_name, "<->" if self.is_bidirectional else "->", end_name
        )
        return route_name

    def price_per_volume_modifier(self):
        """returns the effective price per volume modifier or None """
        if not self.use_price_per_volume_modifier:
            modifier = None

        else:
            handler = ContractHandler.objects.first()
            if handler:
                modifier = handler.price_per_volume_modifier

            else:
                modifier = None

        return modifier

    def price_per_volume_eff(self):
        """"returns price per volume incl. potential modifier or None"""
        if not self.price_per_volume:
            price_per_volume = None
        else:
            price_per_volume = self.price_per_volume
            modifier = self.price_per_volume_modifier()
            if modifier:
                price_per_volume = max(
                    0, price_per_volume + (price_per_volume * modifier / 100)
                )

        return price_per_volume

    def requires_volume(self) -> bool:
        """whether this pricing required volume to be specified"""
        return (self.price_per_volume is not None and self.price_per_volume != 0) or (
            self.volume_min is not None and self.volume_min != 0
        )

    def requires_collateral(self) -> bool:
        """whether this pricing required collateral to be specified"""
        return (
            self.price_per_collateral_percent is not None
            and self.price_per_collateral_percent != 0
        ) or (self.collateral_min is not None and self.collateral_min != 0)

    def is_fix_price(self) -> bool:
        """whether this pricing is a fix price"""
        return (
            self.price_base is not None
            and self.price_min is None
            and self.price_per_volume is None
            and self.price_per_collateral_percent is None
        )

    def clean(self):
        if (
            self.price_base is None
            and self.price_min is None
            and self.price_per_volume is None
            and self.price_per_collateral_percent is None
        ):
            raise ValidationError("You must specify at least one price component")

        if self.start_location_id and self.end_location_id:
            if (
                Pricing.objects.filter(
                    start_location=self.end_location,
                    end_location=self.start_location,
                    is_bidirectional=True,
                ).exists()
                and self.is_bidirectional
            ):
                raise ValidationError(
                    "There already exists a bidirectional pricing for this route. "
                    "Please set this pricing to non-bidirectional to save it. "
                    "And after you must also set the other pricing to "
                    "non-bidirectional."
                )

            if (
                Pricing.objects.filter(
                    start_location=self.end_location,
                    end_location=self.start_location,
                    is_bidirectional=False,
                ).exists()
                and self.is_bidirectional
            ):
                raise ValidationError(
                    "There already exists a non bidirectional pricing for "
                    "this route. You need to mark this pricing as "
                    "non-bidirectional too to continue."
                )

    def get_calculated_price(self, volume: float, collateral: float) -> float:
        """returns the calculated price for the given parameters"""

        if not volume:
            volume = 0

        if not collateral:
            collateral = 0

        if volume < 0:
            raise ValueError("volume can not be negative")
        if collateral < 0:
            raise ValueError("collateral can not be negative")

        volume = float(volume)
        collateral = float(collateral)

        price_base = 0 if not self.price_base else self.price_base
        price_min = 0 if not self.price_min else self.price_min

        price_per_volume_eff = self.price_per_volume_eff()
        if not price_per_volume_eff:
            price_per_volume = 0
        else:
            price_per_volume = price_per_volume_eff

        price_per_collateral_percent = (
            0
            if not self.price_per_collateral_percent
            else self.price_per_collateral_percent
        )

        return max(
            price_min,
            (
                price_base
                + volume * price_per_volume
                + collateral * (price_per_collateral_percent / 100)
            ),
        )

    def get_contract_price_check_issues(
        self, volume: float, collateral: float, reward: float = None
    ) -> list:
        """returns list of validation error messages or none if ok"""

        if volume and volume < 0:
            raise ValueError("volume can not be negative")
        if collateral and collateral < 0:
            raise ValueError("collateral can not be negative")
        if reward and reward < 0:
            raise ValueError("reward can not be negative")

        issues = list()

        if volume is not None and self.volume_min and volume < self.volume_min:
            issues.append(
                "below the minimum required volume of {:,.0f} m3".format(
                    self.volume_min
                )
            )

        if volume is not None and self.volume_max and volume > self.volume_max:
            issues.append(
                "exceeds the maximum allowed volume of {:,.0f} m3".format(
                    self.volume_max
                )
            )

        if (
            collateral is not None
            and self.collateral_max
            and collateral > self.collateral_max
        ):
            issues.append(
                "exceeds the maximum allowed collateral of {:,.0f} ISK".format(
                    self.collateral_max
                )
            )

        if (
            collateral is not None
            and self.collateral_min
            and collateral < self.collateral_min
        ):
            issues.append(
                "below the minimum required collateral of {:,.0f} ISK".format(
                    self.collateral_min
                )
            )

        if reward is not None:
            calculated_price = self.get_calculated_price(volume, collateral)
            if reward < calculated_price:
                issues.append(
                    "reward is below the calculated price of {:,.0f} ISK".format(
                        calculated_price
                    )
                )

        if len(issues) == 0:
            return None
        else:
            return issues


class EveEntity(models.Model):
    """An Eve entity like a corporation or a character"""

    # entity categories supported by this class
    CATEGORY_ALLIANCE = "alliance"
    CATEGORY_CORPORATION = "corporation"
    CATEGORY_CHARACTER = "character"
    CATEGORIES_DEF = [
        (CATEGORY_ALLIANCE, "Alliance"),
        (CATEGORY_CORPORATION, "Corporation"),
        (CATEGORY_CHARACTER, "Character"),
    ]

    AVATAR_SIZE = 128

    id = models.IntegerField(primary_key=True, validators=[MinValueValidator(0)],)
    category = models.CharField(max_length=32, choices=CATEGORIES_DEF,)
    name = models.CharField(max_length=254)

    objects = EveEntityManager()

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return "{}(id={}, category='{}', name='{}')".format(
            self.__class__.__name__, self.id, self.category, self.name
        )

    @property
    def is_alliance(self) -> bool:
        return self.category == self.CATEGORY_ALLIANCE

    @property
    def is_corporation(self) -> bool:
        return self.category == self.CATEGORY_CORPORATION

    @property
    def is_character(self) -> bool:
        return self.category == self.CATEGORY_CHARACTER

    @property
    def avatar_url(self) -> str:
        """returns the url to an icon image for this organization"""
        if self.category == self.CATEGORY_ALLIANCE:
            return EveAllianceInfo.generic_logo_url(self.id, self.AVATAR_SIZE)

        elif self.category == self.CATEGORY_CORPORATION:
            return EveCorporationInfo.generic_logo_url(self.id, self.AVATAR_SIZE)

        elif self.category == self.CATEGORY_CHARACTER:
            return EveCharacter.generic_portrait_url(self.id, self.AVATAR_SIZE)

        else:
            raise NotImplementedError(
                "Avatar URL not implemented for category %s" % self.category
            )

    @classmethod
    def get_category_for_operation_mode(cls, mode: str) -> str:
        """return organization category related to given operation mode"""
        if mode == FREIGHT_OPERATION_MODE_MY_ALLIANCE:
            return cls.CATEGORY_ALLIANCE
        else:
            return cls.CATEGORY_CORPORATION


class ContractHandler(models.Model):
    """Handler for syncing of contracts belonging to an alliance or corporation"""

    # errors
    ERROR_NONE = 0
    ERROR_TOKEN_INVALID = 1
    ERROR_TOKEN_EXPIRED = 2
    ERROR_INSUFFICIENT_PERMISSIONS = 3
    ERROR_NO_CHARACTER = 4
    ERROR_ESI_UNAVAILABLE = 5
    ERROR_OPERATION_MODE_MISMATCH = 6
    ERROR_UNKNOWN = 99

    ERRORS_LIST = [
        (ERROR_NONE, "No error"),
        (ERROR_TOKEN_INVALID, "Invalid token"),
        (ERROR_TOKEN_EXPIRED, "Expired token"),
        (ERROR_INSUFFICIENT_PERMISSIONS, "Insufficient permissions"),
        (ERROR_NO_CHARACTER, "No character set for fetching alliance contacts"),
        (ERROR_ESI_UNAVAILABLE, "ESI API is currently unavailable"),
        (
            ERROR_OPERATION_MODE_MISMATCH,
            "Operaton mode does not match with current setting",
        ),
        (ERROR_UNKNOWN, "Unknown error"),
    ]

    organization = models.OneToOneField(
        EveEntity, on_delete=models.CASCADE, primary_key=True
    )
    character = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        help_text="character used for syncing contracts",
    )
    operation_mode = models.CharField(
        max_length=32,
        default=FREIGHT_OPERATION_MODE_MY_ALLIANCE,
        help_text="defines what kind of contracts are synced",
    )
    price_per_volume_modifier = models.FloatField(
        default=None,
        null=True,
        blank=True,
        help_text=("global modifier for price per volume in percent, e.g. 2.5 = +2.5%"),
    )
    version_hash = models.CharField(
        max_length=32,
        null=True,
        default=None,
        blank=True,
        help_text="hash to identify changes to contracts",
    )
    last_sync = models.DateTimeField(
        null=True, default=None, blank=True, help_text="when the last sync happened"
    )
    last_error = models.IntegerField(
        choices=ERRORS_LIST,
        default=ERROR_NONE,
        help_text="error that occurred at the last sync atttempt (if any)",
    )

    def __str__(self):
        return str(self.organization.name)

    def __repr__(self) -> str:
        return "{}(pk={}, organization='{}')".format(
            self.__class__.__name__, self.pk, str(self.organization.name)
        )

    @property
    def operation_mode_friendly(self) -> str:
        """returns user friendly description of operation mode"""
        msg = [(x, y) for x, y in FREIGHT_OPERATION_MODES if x == self.operation_mode]
        if len(msg) != 1:
            raise ValueError("Undefined mode")
        else:
            return msg[0][1]

    @property
    def last_error_message_friendly(self) -> str:
        msg = [(x, y) for x, y in self.ERRORS_LIST if x == self.last_error]
        return msg[0][1] if len(msg) > 0 else "Undefined error"

    @classmethod
    def get_esi_scopes(cls) -> list:
        return [
            "esi-contracts.read_corporation_contracts.v1",
            "esi-universe.read_structures.v1",
        ]

    @property
    def is_sync_ok(self) -> bool:
        """returns true if they have been no errors
        and last syncing occurred within alloted time
        """
        return (
            self.last_error == self.ERROR_NONE
            and self.last_sync
            and self.last_sync
            > (now() - timedelta(minutes=FREIGHT_CONTRACT_SYNC_GRACE_MINUTES))
        )

    class Meta:
        verbose_name_plural = verbose_name = "Contract Handler"

    def get_availability_text_for_contracts(self) -> str:
        """returns a text detailing the availability choice for this setup"""

        if self.operation_mode == FREIGHT_OPERATION_MODE_MY_ALLIANCE:
            extra_text = "[My Alliance]"

        elif self.operation_mode == FREIGHT_OPERATION_MODE_MY_CORPORATION:
            extra_text = "[My Corporation]"

        else:
            extra_text = ""

        return "Private ({}) {}".format(self.organization.name, extra_text)

    def set_sync_status(self, error: int = None) -> None:
        """sets the sync status incl. sync time and saves the object. 
        
        Will set to no error if no error is provided as argument.
        """
        if not error:
            error = self.ERROR_NONE

        self.last_error = error
        self.last_sync = now()
        self.save()

    def token(self) -> Token:
        """returns an esi token for the contract handler
        
        raises exception on error
        """
        add_prefix = make_logger_prefix(self)
        try:
            token = (
                Token.objects.filter(
                    user=self.character.user,
                    character_id=self.character.character.character_id,
                )
                .require_scopes(self.get_esi_scopes())
                .require_valid()
                .first()
            )

        except TokenInvalidError:
            logger.error(add_prefix("Invalid token for fetching contracts"))
            self.set_sync_status(self.ERROR_TOKEN_INVALID)
            raise TokenInvalidError()

        except TokenExpiredError:
            logger.error(add_prefix("Token expired for fetching contracts"))
            self.set_sync_status(self.ERROR_TOKEN_EXPIRED)
            raise TokenExpiredError()

        else:
            if not token:
                logger.error(add_prefix("No valid token found"))
                self.set_sync_status(self.ERROR_TOKEN_INVALID)
                raise TokenInvalidError()

        logger.info(add_prefix("Fetching ESI client..."))
        return token

    def update_contracts_esi(self, force_sync=False, user=None) -> bool:
        try:
            add_prefix = make_logger_prefix(self)
            self._validate_update_readiness()
            token = self.token()
            try:
                # fetching data from ESI
                contracts = esi_fetch(
                    "Contracts.get_corporations_corporation_id_contracts",
                    args={"corporation_id": self.character.character.corporation_id},
                    has_pages=True,
                    token=token,
                    logger_tag=add_prefix(),
                )

                if settings.DEBUG:
                    self._save_contract_to_file(contracts)

                self._process_contracts_from_esi(contracts, token, force_sync)

            except Exception as ex:
                logger.exception(
                    add_prefix("An unexpected error ocurred {}".format(ex))
                )
                self.set_sync_status(self.ERROR_UNKNOWN)
                raise ex

        except Exception as ex:
            success = False
            error_code = type(ex).__name__

        else:
            success = True
            error_code = None

        if user:
            self._report_to_user(user, success, error_code)

        return success

    def _validate_update_readiness(self):
        add_prefix = make_logger_prefix(self)

        # abort if operation mode from settings is different
        if self.operation_mode != FREIGHT_OPERATION_MODE:
            logger.error(add_prefix("Current operation mode not matching the handler"))

            self.set_sync_status(self.ERROR_OPERATION_MODE_MISMATCH)
            raise ValueError()

        # abort if character is not configured
        if self.character is None:
            logger.error(add_prefix("No character configured to sync"))
            self.set_sync_status(self.ERROR_NO_CHARACTER)
            raise ValueError()

        # abort if character does not have sufficient permissions
        if not self.character.user.has_perm("freight.setup_contract_handler"):
            logger.error(
                add_prefix(
                    "Character does not have sufficient permission to sync contracts"
                )
            )
            self.set_sync_status(self.ERROR_INSUFFICIENT_PERMISSIONS)
            raise ValueError()

    def _save_contract_to_file(self, contracts):
        """saves raw contracts to file for debugging"""
        with open("contracts_raw.json", "w", encoding="utf-8") as f:
            json.dump(contracts, f, cls=DjangoJSONEncoder, sort_keys=True, indent=4)

    def _process_contracts_from_esi(
        self, contracts_all: list, token: object, force_sync: bool
    ):
        add_prefix = make_logger_prefix(self)

        # 1st filter: reduce to courier contracts assigned to handler org
        contracts_courier = [
            x
            for x in contracts_all
            if x["type"] == "courier"
            and int(x["assignee_id"]) == int(self.organization.id)
        ]

        # 2nd filter: remove contracts not in scope due to operation mode
        contracts = list()
        for contract in contracts_courier:
            try:
                issuer = EveCharacter.objects.get(character_id=contract["issuer_id"])
            except EveCharacter.DoesNotExist:
                issuer = EveCharacter.objects.create_character(
                    character_id=contract["issuer_id"]
                )

            assignee_id = int(contract["assignee_id"])
            issuer_corporation_id = int(issuer.corporation_id)
            issuer_alliance_id = int(issuer.alliance_id) if issuer.alliance_id else None

            if self.operation_mode == FREIGHT_OPERATION_MODE_MY_ALLIANCE:
                in_scope = issuer_alliance_id == assignee_id

            elif self.operation_mode == FREIGHT_OPERATION_MODE_MY_CORPORATION:
                in_scope = assignee_id == issuer_corporation_id

            elif self.operation_mode == FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE:
                in_scope = issuer_alliance_id == int(
                    self.character.character.alliance_id
                )

            elif self.operation_mode == FREIGHT_OPERATION_MODE_CORP_PUBLIC:
                in_scope = True

            else:
                raise NotImplementedError(
                    "Unsupported operation mode: {}".format(self.operation_mode)
                )
            if in_scope:
                contracts.append(contract)

        # determine if contracts have changed by comparing their hashes
        new_version_hash = hashlib.md5(
            json.dumps(contracts, cls=DjangoJSONEncoder).encode("utf-8")
        ).hexdigest()
        if force_sync or new_version_hash != self.version_hash:
            self._store_contract_from_esi(contracts, new_version_hash, token)

        else:
            logger.info(add_prefix("Contracts are unchanged."))
            self.set_sync_status(ContractHandler.ERROR_NONE)

    def _store_contract_from_esi(
        self, contracts: list, new_version_hash: str, token: Token
    ) -> None:
        add_prefix = make_logger_prefix(self)
        logger.info(
            add_prefix("Storing update with {:,} contracts".format(len(contracts)))
        )

        # update contracts in local DB
        with transaction.atomic():
            self.version_hash = new_version_hash
            no_errors = True
            for contract in contracts:
                try:
                    Contract.objects.update_or_create_from_dict(
                        handler=self, contract=contract, token=token
                    )
                except Exception as ex:
                    logger.exception(
                        add_prefix(
                            "An unexpected error ocurred "
                            "while trying to load contract "
                            "{}: {}".format(
                                contract["contract_id"]
                                if "contract_id" in contract
                                else "Unknown",
                                ex,
                            )
                        )
                    )
                    no_errors = False

            if no_errors:
                last_error = self.ERROR_NONE
            else:
                last_error = self.ERROR_UNKNOWN
            self.set_sync_status(last_error)

        Contract.objects.update_pricing()

    def _report_to_user(self, user, success, error_code):
        add_prefix = make_logger_prefix(self)
        try:
            message = 'Syncing of contracts for "{}"'.format(self.organization.name)
            message += ' in operation mode "{}" {}.\n'.format(
                self.operation_mode_friendly,
                "completed successfully" if success else "has failed",
            )
            if success:
                message += "{:,} contracts synced.".format(self.contract_set.count())
            else:
                message += "Error code: {}".format(error_code)

            notify(
                user=user,
                title="Freight: Contracts sync for {}: {}".format(
                    self.organization.name, "OK" if success else "FAILED"
                ),
                message=message,
                level="success" if success else "danger",
            )
        except Exception as ex:
            logger.exception(
                add_prefix(
                    "An unexpected error ocurred while trying to "
                    + "report to user: {}".format(ex)
                )
            )


class Contract(models.Model):
    """An Eve Online courier contract with additional meta data"""

    STATUS_OUTSTANDING = "outstanding"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_FINISHED_ISSUER = "finished_issuer"
    STATUS_FINISHED_CONTRACTOR = "finished_contractor"
    STATUS_FINISHED = "finished"
    STATUS_CANCELED = "canceled"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_DELETED = "deleted"
    STATUS_REVERSED = "reversed"

    STATUS_CHOICES = [
        (STATUS_OUTSTANDING, "outstanding"),
        (STATUS_IN_PROGRESS, "in progress"),
        (STATUS_FINISHED_ISSUER, "finished issuer"),
        (STATUS_FINISHED_CONTRACTOR, "finished contractor"),
        (STATUS_FINISHED, "finished"),
        (STATUS_CANCELED, "canceled"),
        (STATUS_REJECTED, "rejected"),
        (STATUS_FAILED, "failed"),
        (STATUS_DELETED, "deleted"),
        (STATUS_REVERSED, "reversed"),
    ]
    STATUS_FOR_CUSTOMER_NOTIFICATION = [
        STATUS_OUTSTANDING,
        STATUS_IN_PROGRESS,
        STATUS_FINISHED,
        STATUS_FAILED,
    ]

    EMBED_COLOR_PASSED = 0x008000
    EMBED_COLOR_FAILED = 0xFF0000

    handler = models.ForeignKey(ContractHandler, on_delete=models.CASCADE)
    contract_id = models.IntegerField()

    acceptor = models.ForeignKey(
        EveCharacter,
        on_delete=models.CASCADE,
        default=None,
        null=True,
        blank=True,
        related_name="contract_acceptor",
        help_text="character of acceptor or None if accepted by corp",
    )
    acceptor_corporation = models.ForeignKey(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        default=None,
        null=True,
        blank=True,
        related_name="contract_acceptor_corporation",
        help_text="corporation of acceptor",
    )
    collateral = models.FloatField()
    date_accepted = models.DateTimeField(default=None, null=True, blank=True)
    date_completed = models.DateTimeField(default=None, null=True, blank=True)
    date_expired = models.DateTimeField()
    date_issued = models.DateTimeField()
    days_to_complete = models.IntegerField()
    end_location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="contract_end_location"
    )
    for_corporation = models.BooleanField()
    issuer_corporation = models.ForeignKey(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        related_name="contract_issuer_corporation",
    )
    issuer = models.ForeignKey(
        EveCharacter, on_delete=models.CASCADE, related_name="contract_issuer"
    )
    reward = models.FloatField()
    start_location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="contract_start_location"
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    title = models.CharField(max_length=100, default=None, null=True, blank=True)
    volume = models.FloatField()
    pricing = models.ForeignKey(
        Pricing, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True
    )
    date_notified = models.DateTimeField(
        default=None,
        null=True,
        blank=True,
        help_text="datetime of latest notification, None = none has been sent",
    )
    issues = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="List or price check issues as JSON array of strings or None",
    )

    objects = ContractManager()

    def __str__(self) -> str:
        return "{}: {} -> {}".format(
            self.contract_id,
            self.start_location.solar_system_name,
            self.end_location.solar_system_name,
        )

    def __repr__(self) -> str:
        return "{}(contract_id={}, start_location={}, end_location={})".format(
            self.__class__.__name__,
            self.contract_id,
            self.start_location.solar_system_name,
            self.end_location.solar_system_name,
        )

    class Meta:
        unique_together = (("handler", "contract_id"),)
        indexes = [
            models.Index(fields=["status"]),
        ]

    @property
    def is_completed(self) -> bool:
        """whether this contract is completed or active"""
        return self.status in [
            self.STATUS_FINISHED_ISSUER,
            self.STATUS_FINISHED_CONTRACTOR,
            self.STATUS_FINISHED_ISSUER,
            self.STATUS_CANCELED,
            self.STATUS_REJECTED,
            self.STATUS_DELETED,
            self.STATUS_FINISHED,
            self.STATUS_FAILED,
        ]

    @property
    def is_in_progress(self) -> bool:
        return self.status == self.STATUS_IN_PROGRESS

    @property
    def is_failed(self) -> bool:
        return self.status == self.STATUS_FAILED

    @property
    def has_expired(self) -> bool:
        """returns true if this contract is expired"""
        return self.date_expired < now()

    @property
    def has_pricing(self) -> bool:
        return bool(self.pricing)

    @property
    def has_pricing_errors(self) -> bool:
        return bool(self.issues)

    @property
    def hours_issued_2_completed(self) -> float:
        if self.date_completed:
            td = self.date_completed - self.date_issued
            return td.days * 24 + (td.seconds / 3600)
        else:
            return None

    @property
    def date_latest(self) -> bool:
        """latest status related date of this contract"""
        if self.date_completed:
            date = self.date_completed
        elif self.date_accepted:
            date = self.date_accepted
        else:
            date = self.date_issued

        return date

    @property
    def has_stale_status(self) -> bool:
        """whether the status of this contract has become stale"""
        return self.date_latest < now() - timedelta(
            hours=FREIGHT_HOURS_UNTIL_STALE_STATUS
        )

    @property
    def acceptor_name(self) -> str:
        "returns the name of the acceptor character or corporation or None"

        if self.acceptor:
            name = self.acceptor.character_name
        elif self.acceptor_corporation:
            name = self.acceptor_corporation.corporation_name
        else:
            name = None

        return name

    def get_price_check_issues(self, pricing: Pricing) -> list:
        return pricing.get_contract_price_check_issues(
            self.volume, self.collateral, self.reward
        )

    def get_issue_list(self) -> list:
        """returns current pricing issues as list of strings"""
        if self.issues:
            return json.loads(self.issues)
        else:
            return []

    def _generate_embed(self) -> Embed:
        """generates a Discord embed for this contract"""
        desc = ""
        desc += "**Route**: {} <-> {}\n".format(
            self.start_location.solar_system_name, self.end_location.solar_system_name
        )
        desc += "**Reward**: {:,.0f} M ISK\n".format(self.reward / 1000000)
        desc += "**Collateral**: {:,.0f} M ISK\n".format(self.collateral / 1000000)
        desc += "**Volume**: {:,.0f} m3\n".format(self.volume)
        desc += "**Status**: {}\n".format(self.status)
        if self.pricing:
            if not self.has_pricing_errors:
                check_text = "passed"
                color = self.EMBED_COLOR_PASSED
            else:
                check_text = "FAILED"
                color = self.EMBED_COLOR_FAILED
        else:
            check_text = "N/A"
            color = None
        desc += "**Contract Check**: {}\n".format(check_text)
        desc += "**Issued on**: {}\n".format(self.date_issued.strftime(DATETIME_FORMAT))
        desc += "**Issued by**: {}\n".format(self.issuer)
        desc += "**Expires on**: {}\n".format(
            self.date_expired.strftime(DATETIME_FORMAT)
        )
        if self.acceptor_name:
            desc += "**Accepted by**: {}\n".format(self.acceptor_name)
        if self.date_accepted:
            desc += "**Accepted on**: {}\n".format(
                self.date_accepted.strftime(DATETIME_FORMAT)
            )

        return Embed(
            description=desc,
            color=color,
            thumbnail=Thumbnail(self.issuer.portrait_url()),
        )

    def get_logger_tag(self):
        return make_logger_prefix("contract:{}".format(self.contract_id))

    def send_pilot_notification(self):
        """sends pilot notification about this contract to the DISCORD webhook"""
        add_tag = self.get_logger_tag()
        if FREIGHT_DISCORD_WEBHOOK_URL:
            if FREIGHT_DISCORD_DISABLE_BRANDING:
                username = None
                avatar_url = None
            else:
                username = FREIGHT_APP_NAME
                avatar_url = self.handler.organization.avatar_url

            hook = Webhook(
                FREIGHT_DISCORD_WEBHOOK_URL, username=username, avatar_url=avatar_url
            )
            with transaction.atomic():
                logger.info(
                    add_tag(
                        "Trying to sent pilot notification about "
                        "contract {} to {}".format(
                            self.contract_id, FREIGHT_DISCORD_WEBHOOK_URL
                        )
                    )
                )
                if FREIGHT_DISCORD_MENTIONS:
                    contents = str(FREIGHT_DISCORD_MENTIONS) + " "
                else:
                    contents = ""

                contract_list_url = urljoin(
                    get_site_base_url(), reverse("freight:contract_list_active")
                )
                contents += (
                    "There is a new courier contract from {} "
                    "looking to be picked up "
                    "[[show]({})]:"
                ).format(self.issuer, contract_list_url)

                embed = self._generate_embed()
                response = hook.execute(
                    content=contents, embeds=[embed], wait_for_response=True
                )
                if response.status_ok:
                    self.date_notified = now()
                    self.save()
                else:
                    logger.warn(
                        add_tag(
                            "Failed to send message. HTTP code: {}".format(
                                response.status_code
                            )
                        )
                    )
        else:
            logger.debug(add_tag("FREIGHT_DISCORD_WEBHOOK_URL not configured"))

    def send_customer_notification(self, force_sent=False):
        """sends customer notification about this contract to Discord
        force_sent: send notification even if one has already been sent
        """
        if FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL and "discord" in app_labels():
            status_to_report = None
            for status in self.STATUS_FOR_CUSTOMER_NOTIFICATION:
                if self.status == status and (
                    force_sent
                    or not self.contractcustomernotification_set.filter(
                        status__exact=status
                    )
                ):
                    status_to_report = status
                    break

            if status_to_report:
                self._report_to_customer(status_to_report)
        else:
            add_tag = self.get_logger_tag()
            logger.debug(
                add_tag(
                    "FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL not configured or "
                    "Discord services not installed"
                )
            )

    def _report_to_customer(self, status_to_report):
        add_tag = self.get_logger_tag()
        issuer_user = User.objects.filter(
            character_ownerships__character__exact=self.issuer
        ).first()

        if not issuer_user:
            logger.info(add_tag("Could not find matching user for issuer"))
            return

        try:
            discord_user = DiscordUser.objects.get(user=issuer_user)
            discord_user_id = discord_user.uid

        except DiscordUser.DoesNotExist:
            logger.info(add_tag("Could not find Discord user for issuer"))
            return

        if FREIGHT_DISCORD_DISABLE_BRANDING:
            username = None
            avatar_url = None
        else:
            username = FREIGHT_APP_NAME
            avatar_url = self.handler.organization.avatar_url

        hook = Webhook(
            FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL,
            username=username,
            avatar_url=avatar_url,
        )
        with transaction.atomic():
            logger.info(
                add_tag(
                    "Trying to sent customer notification"
                    " about contract {} on status {}"
                    " to {}".format(
                        self.contract_id,
                        status_to_report,
                        FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL,
                    )
                )
            )
            embed = self._generate_embed()
            contents = self._generate_contents(discord_user_id, status_to_report)
            response = hook.execute(
                content=contents, embeds=[embed], wait_for_response=True
            )
            if response.status_ok:
                ContractCustomerNotification.objects.update_or_create(
                    contract=self,
                    status=status_to_report,
                    defaults={"date_notified": now()},
                )

            else:
                logger.warn(
                    add_tag(
                        "Failed to send message. HTTP code: {}".format(
                            response.status_code
                        )
                    )
                )

    def _generate_contents(self, discord_user_id, status_to_report):
        contents = "<@{}>\n".format(discord_user_id)
        if self.acceptor_name:
            acceptor_text = "by {} ".format(self.acceptor_name)
        else:
            acceptor_text = ""
        if status_to_report == self.STATUS_OUTSTANDING:
            contents += "We have received your contract"
            if self.has_pricing_errors:
                issues = self.get_issue_list()
                contents += (
                    ", but we found some issues.\n"
                    "Please create a new courier contract "
                    "and correct the following issues:\n"
                )
                for issue in issues:
                    contents += "• {}\n".format(issue)
            else:
                contents += " and it will be picked up by " "one of our pilots shortly."

        elif status_to_report == self.STATUS_IN_PROGRESS:
            contents += (
                "Your contract has been picked up {}"
                "and will be delivered to you shortly.".format(acceptor_text)
            )

        elif status_to_report == self.STATUS_FINISHED:
            contents += (
                "Your contract has been **delivered**.\n"
                "Thank you for using our freight service."
            )

        elif status_to_report == self.STATUS_FAILED:
            contents += (
                "Your contract has been **failed** {}"
                "Thank you for using our freight service.".format(acceptor_text)
            )

        else:
            raise NotImplementedError()

        contents += (
            "\nClick [here]({}) to check the current " "status of your contract."
        ).format(urljoin(get_site_base_url(), reverse("freight:contract_list_user")))
        return contents


class ContractCustomerNotification(models.Model):
    """record of contract notification to customer about state"""

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, choices=Contract.STATUS_CHOICES)
    date_notified = models.DateTimeField(help_text="datetime of notification")

    class Meta:
        unique_together = (("contract", "status"),)

    def __str__(self):
        return "{} - {}".format(self.contract.contract_id, self.status)

    def __repr__(self) -> str:
        return "{}(pk={}, contract_id={}, status={})".format(
            self.__class__.__name__, self.pk, self.contract.contract_id, self.status
        )
