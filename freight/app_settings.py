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
