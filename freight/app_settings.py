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
