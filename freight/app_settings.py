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

# If and how notifications are pinging on Discord
# Valid values are: None, '@here' and '@everyone'.
FREIGHT_DISCORD_PING_TYPE = getattr(
    settings, 
    'FREIGHT_DISCORD_PING_TYPE', 
    None
)

# modes of operation for Alliance Freight
FREIGHT_OPERATION_MODE_MY_ALLIANCE = 'my_alliance'
FREIGHT_OPERATION_MODE_MY_CORPORATION = 'my_corporation'
FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE = 'corp_in_alliance'

FREIGHT_OPERATION_MODES = [
    (FREIGHT_OPERATION_MODE_MY_ALLIANCE, 'My Alliance'),
    (FREIGHT_OPERATION_MODE_MY_CORPORATION, 'My Corporation'),
    (FREIGHT_OPERATION_MODE_CORP_IN_ALLIANCE, 'Corporation in my Alliance'),
]

if (hasattr(settings, 'FREIGHT_OPERATION_MODE') 
    and settings.FREIGHT_OPERATION_MODE in [x[0] for x in FREIGHT_OPERATION_MODES]):
    FREIGHT_OPERATION_MODE = settings.FREIGHT_OPERATION_MODE
else:
    FREIGHT_OPERATION_MODE = FREIGHT_OPERATION_MODE_MY_ALLIANCE

def get_freight_operation_mode_friendly(mode: str) -> str:
    """returns user friendly description of operation mode"""    
    msg = [(x, y) for x, y in FREIGHT_OPERATION_MODES if x == mode]
    if len(msg) != 1:
        raise ValueError('Undefined mode')
    else:
        return msg[0][1]