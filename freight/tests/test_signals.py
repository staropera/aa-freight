from unittest.mock import Mock, patch
from time import sleep

from django.db.models import signals
from django.test import TestCase

from . import set_logger
from ..models import *
from .testdata import create_contract_handler_w_contracts

logger = set_logger('freight.signals', __file__)


class TestSignals(TestCase):

    def setUp(self):
        self.user = create_contract_handler_w_contracts([
            149409016
        ])
        from .. import signals

    
    @patch('freight.signals.update_contracts_pricing')
    def test_pricing_save_handler(self, mock_update_contracts_pricing):                
        jita = Location.objects.get(id=60003760)
        amamake = Location.objects.get(id=1022167642188)
        
        pricing_1 = Pricing.objects.create(
            start_location=jita,
            end_location=amamake,
            price_base=500000000
        )        
        sleep(1)
        
        self.assertTrue(mock_update_contracts_pricing.delay.called)
