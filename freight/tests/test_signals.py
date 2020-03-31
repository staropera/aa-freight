from unittest.mock import patch
from time import sleep

from ..models import Location, Pricing
from .testdata import create_contract_handler_w_contracts
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'freight.signals'
logger = set_test_logger(MODULE_PATH, __file__)


class TestSignals(NoSocketsTestCase):

    def setUp(self):
        self.user = create_contract_handler_w_contracts([149409016])
        from .. import signals  # noqa

    @patch(MODULE_PATH + '.update_contracts_pricing')
    def test_pricing_save_handler(self, mock_update_contracts_pricing):                
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        
        Pricing.objects.create(
            start_location=jita,
            end_location=amamake,
            price_base=500000000
        )        
        sleep(1)
        
        self.assertTrue(mock_update_contracts_pricing.delay.called)
