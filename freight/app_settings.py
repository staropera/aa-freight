from django.conf import settings

# Webhook URL used for notifications if defined
FREIGHT_DISCORD_WEBHOOK_URL = getattr(
    settings, 
    'FREIGHT_DISCORD_WEBHOOK_URL', 
    None
)

# Will be shown as avatar icon for Discord notifications if defined
FREIGHT_DISCORD_AVATAR_URL = getattr(
    settings, 
    'FREIGHT_DISCORD_AVATAR_URL', 
    None
)

# If and how notifications are pinging on Discord
# Valid values are: None, '@here' and '@everyone'.
FREIGHT_DISCORD_PING_TYPE = getattr(
    settings, 
    'FREIGHT_DISCORD_PING_TYPE', 
    None
)

# mode of operation for Alliance Freight
FREIGHT_OPERATION_MODE_MY_ALLIANCE = 'my_alliance'
FREIGHT_OPERATION_MODE_MY_CORPORATION = 'my_corporation'
_FREIGHT_OPERATION_MODES_DEF = [
    FREIGHT_OPERATION_MODE_MY_ALLIANCE,
    FREIGHT_OPERATION_MODE_MY_CORPORATION
]

if (hasattr(settings, 'FREIGHT_OPERATION_MODE') 
    and settings.FREIGHT_OPERATION_MODE in (_FREIGHT_OPERATION_MODES_DEF)):
    FREIGHT_OPERATION_MODE = settings.FREIGHT_OPERATION_MODE
else:
    FREIGHT_OPERATION_MODE = FREIGHT_OPERATION_MODE_MY_ALLIANCE

# define app title based on operation mode
if FREIGHT_OPERATION_MODE == FREIGHT_OPERATION_MODE_MY_CORPORATION:
    FREIGHT_APP_TITLE = 'Corporation Freight'
else:
    FREIGHT_APP_TITLE = 'Alliance Freight'