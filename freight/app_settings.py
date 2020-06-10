from django.conf import settings
from .utils import clean_setting

# Name of this app as shown in the Auth sidebar, page titles
# and as default avatar name for notifications
FREIGHT_APP_NAME = clean_setting(
    "FREIGHT_APP_NAME", "Alliance Freight", required_type=str
)

# Sets the number minutes until a delayed sync will be recognized as error
FREIGHT_CONTRACT_SYNC_GRACE_MINUTES = clean_setting(
    "FREIGHT_CONTRACT_SYNC_GRACE_MINUTES", 30
)


# Enables features for developers, e.g. write access to all models in admin
FREIGHT_DEVELOPER_MODE = clean_setting("FREIGHT_DEVELOPER_MODE", False)


# Webhook URL used for notifications if defined
FREIGHT_DISCORD_WEBHOOK_URL = clean_setting(
    "FREIGHT_DISCORD_WEBHOOK_URL", None, required_type=str
)


# Will be shown as "user name" instead of what is configured as app name
# for notifications if defined
FREIGHT_DISCORD_AVATAR_NAME = clean_setting(
    "FREIGHT_DISCORD_AVATAR_NAME", None, required_type=str
)


# when set true will no longer set name and avatar for webhooks
FREIGHT_DISCORD_DISABLE_BRANDING = clean_setting(
    "FREIGHT_DISCORD_DISABLE_BRANDING", False
)


# Mentions to appear upfront to any notification
# Typical values are: None, '@here' and '@everyone'.
FREIGHT_DISCORD_MENTIONS = clean_setting(
    "FREIGHT_DISCORD_MENTIONS", None, required_type=str
)


# max days back considered when calculating statistics
FREIGHT_STATISTICS_MAX_DAYS = clean_setting(
    "FREIGHT_STATISTICS_MAX_DAYS", 90, min_value=1
)

# Webhook URL used for notifications to customers if defined
FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL = clean_setting(
    "FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL", None, required_type=str
)


# defines after how many hours a status becomes stale
# a stale status will not be reported to customers
FREIGHT_HOURS_UNTIL_STALE_STATUS = clean_setting("FREIGHT_HOURS_UNTIL_STALE_STATUS", 24)


# Whether to show full location names in the route dropdown of the calculator
FREIGHT_FULL_ROUTE_NAMES = clean_setting("FREIGHT_FULL_ROUTE_NAMES", False)

# whether created timers are corp restricted on the timerboard
FREIGHT_ESI_TIMEOUT_ENABLED = clean_setting("FREIGHT_ESI_TIMEOUT_ENABLED", True)

# modes of operation for Alliance Freight
FREIGHT_OPERATION_MODE_MY_ALLIANCE = "my_alliance"
FREIGHT_OPERATION_MODE_MY_CORPORATION = "my_corporation"
FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE = "corp_in_alliance"
FREIGHT_OPERATION_MODE_CORP_PUBLIC = "corp_public"

FREIGHT_OPERATION_MODES = [
    (FREIGHT_OPERATION_MODE_MY_ALLIANCE, "My Alliance"),
    (FREIGHT_OPERATION_MODE_MY_CORPORATION, "My Corporation"),
    (FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE, "Corporation in my Alliance"),
    (FREIGHT_OPERATION_MODE_CORP_PUBLIC, "Corporation public"),
]

if hasattr(settings, "FREIGHT_OPERATION_MODE") and settings.FREIGHT_OPERATION_MODE in [
    x[0] for x in FREIGHT_OPERATION_MODES
]:
    FREIGHT_OPERATION_MODE = settings.FREIGHT_OPERATION_MODE
else:
    FREIGHT_OPERATION_MODE = FREIGHT_OPERATION_MODE_MY_ALLIANCE
