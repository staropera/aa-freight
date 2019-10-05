from django.test import TestCase
from dhooks import Webhook

TEXT_DISCORD_WEBHOOK_URL = 'https://discordapp.com/api/webhooks/590155561958637568/igaptgozG96NpcSCeEZIs6mw5hTthO10_zeTco_sGJoBVQoAXB_ziZprixV_5qf9kpQh'

class TestDiscord(TestCase):

    def test_message_create(self):
        hook = Webhook(TEXT_DISCORD_WEBHOOK_URL, username='Alliance Freight', avatar_url='https://www.kalkoken.org/apps/easypoll/resources/poll-logo.png')
        hook.send("Hello there! I'm a webhook :open_mouth:")

