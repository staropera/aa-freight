import unittest
from unittest.mock import Mock, patch
import discordhook
import datetime

class TestWebhookMock(unittest.TestCase):

    def get_content(self, mock_requests):
        url = None
        json = None
        for x in mock_requests.post.call_args:
            if type(x) == dict and 'url' in x:
                url = x['url']
            if type(x) == dict and 'json' in x:
                json = x['json']

        return url, json
    
    @patch('discordhook.requests', auto_spec=True)
    def test_webhook(self, mock_requests):
                
        hook = discordhook.Webhook('xxx')        
        hook.send('Hi there')
        url, json = self.get_content(mock_requests)
        
        self.assertEqual(url, 'xxx')
        self.assertDictEqual(json, {'content': 'Hi there'})


    @patch('discordhook.requests', auto_spec=True)
    def test_max_embed(self, mock_requests):
        hook = discordhook.Webhook('xxx')
        large_string = 'x' * 6000
        e = discordhook.Embed(description=large_string)
        with self.assertRaises(ValueError):
            hook.send('Hi there', embeds=[e])
        
"""
class TestWebhookReal(unittest.TestCase):

    def test_webhook(self):
        hook = discordhook.Webhook(
            'https://discordapp.com/api/webhooks/590155561958637568/igaptgozG96NpcSCeEZIs6mw5hTthO10_zeTco_sGJoBVQoAXB_ziZprixV_5qf9kpQh',
            # username='Jonny Goodfellow',
            # avatar_url='https://www.0-cal.net/img/alliance-logo.png'
        )
        hook.send('Hello world')

        e = discordhook.Embed(
            title='Dank title',
            description='Can you here me?',
            url='https://www.0-cal.net',
            color=0x5CDBF0,
            # thumbnail_url='https://www.0-cal.net/img/alliance-logo.png',
            timestamp=datetime.datetime.utcnow()
        )
        
        e.add_field(name='size', value='large')
        e.add_field(name='weight', value='medium')

        e.set_footer(
            'Erik Kalkoken', 
            'https://imageserver.eveonline.com/Character/93330670_64.jpg'
        )
        e.set_provider(
            'Erik Kalkokens Killboard', 
            'https://zkillboard.com/character/93330670/'
        )
        r = hook.send('abc', embeds=[e])
        print(r)
"""

if __name__ == '__main__':
    unittest.main()