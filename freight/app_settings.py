from django.conf import settings

FREIGHT_DISCORD_WEBHOOK_URL = getattr(
    settings, 
    'FREIGHT_DISCORD_WEBHOOK_URL', 
    None
)
