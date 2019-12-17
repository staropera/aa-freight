from django.conf import settings

# Webhook URL used for notifications if defined
FREIGHT_DISCORD_WEBHOOK_URL = getattr(
    settings, 
    'FREIGHT_DISCORD_WEBHOOK_URL', 
    None
)

# Will be shown as "user name" instead of "Alliance Freight" for notifications if defined
FREIGHT_DISCORD_AVATAR_NAME = getattr(
    settings, 
    'FREIGHT_DISCORD_AVATAR_NAME', 
    None
)

# when set true will no longer set name and avatar for webhooks
FREIGHT_DISCORD_DISABLE_BRANDING = getattr(
    settings, 
    'FREIGHT_DISCORD_DISABLE_BRANDING', 
    None
)

# Menions to appear upfront to any notification
# Typical values are: None, '@here' and '@everyone'.
FREIGHT_DISCORD_MENTIONS = getattr(
    settings, 
    'FREIGHT_DISCORD_MENTIONS', 
    None
)

# max days back considered when calculating statistics
if (hasattr(settings, 'FREIGHT_STATISTICS_MAX_DAYS')
    and settings.FREIGHT_STATISTICS_MAX_DAYS > 0
):
    FREIGHT_STATISTICS_MAX_DAYS = settings.FREIGHT_STATISTICS_MAX_DAYS
else:
    FREIGHT_STATISTICS_MAX_DAYS = 90


# Webhook URL used for notifications to customers if defined
FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL = getattr(
    settings, 
    'FREIGHT_DISCORD_CUSTOMERS_WEBHOOK_URL', 
    None
)

# Enables features for developers, e.g. write access to all models in admin
FREIGHT_DEVELOPER_MODE = getattr(
    settings, 
    'FREIGHT_DEVELOPER_MODE', 
    False
)

# defines after how many hours a status becomes stale
# a stale status will not be reported to customers
if (hasattr(settings, 'FREIGHT_HOURS_UNTIL_STALE_STATUS')
    and settings.FREIGHT_HOURS_UNTIL_STALE_STATUS > 0
):
    FREIGHT_HOURS_UNTIL_STALE_STATUS = settings.FREIGHT_HOURS_UNTIL_STALE_STATUS
else:
    FREIGHT_HOURS_UNTIL_STALE_STATUS = 24

# Whether to show full location names in the route dropdown of the calculator
FREIGHT_FULL_ROUTE_NAMES = getattr(
    settings, 
    'FREIGHT_FULL_ROUTE_NAMES', 
    False
)

# modes of operation for Alliance Freight
FREIGHT_OPERATION_MODE_MY_ALLIANCE = 'my_alliance'
FREIGHT_OPERATION_MODE_MY_CORPORATION = 'my_corporation'
FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE = 'corp_in_alliance'
FREIGHT_OPERATION_MODE_CORP_PUBLIC = 'corp_public'

FREIGHT_OPERATION_MODES = [
    (FREIGHT_OPERATION_MODE_MY_ALLIANCE, 'My Alliance'),
    (FREIGHT_OPERATION_MODE_MY_CORPORATION, 'My Corporation'),
    (FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE, 'Corporation in my Alliance'),
    (FREIGHT_OPERATION_MODE_CORP_PUBLIC, 'Corporation public'),
]

if (hasattr(settings, 'FREIGHT_OPERATION_MODE') 
    and settings.FREIGHT_OPERATION_MODE in \
        [x[0] for x in FREIGHT_OPERATION_MODES]
):
    FREIGHT_OPERATION_MODE = settings.FREIGHT_OPERATION_MODE
else:
    FREIGHT_OPERATION_MODE = FREIGHT_OPERATION_MODE_MY_ALLIANCE
