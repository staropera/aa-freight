from django.test import TestCase
from .models import *

class TestPricing(TestCase):

    def test_get_calculated_price(self):
        p = Pricing()
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, 0), 
            500
        )

        p = Pricing()        
        p.price_per_collateral_percent = 2
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            20
        )

        p = Pricing()        
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            520
        )

        p = Pricing()
        p.price_base = 20
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            20
        )

        p = Pricing()
        p.price_min = 1000
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            1000
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            520
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_min = 1000
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            1000
        )

        p = Pricing()
        p.price_base = 20
        p.price_per_volume = 50
        p.price_per_collateral_percent = 2
        p.price_min = 500
        self.assertEqual(
            p.get_calculated_price(10, 1000), 
            540
        )

        with self.assertRaises(ValueError):            
            p.get_calculated_price(-5, 0)

        with self.assertRaises(ValueError):            
            p.get_calculated_price(50, -5)

        p = Pricing()
        with self.assertRaises(ValidationError):
            p.get_calculated_price(1, 1)

    
    def test_get_contract_pricing_errors(self):
        p = Pricing()
        p.price_base = 500        
        self.assertIsNone(p.get_contract_pricing_errors(5, 10))
        
        p = Pricing()
        p.price_base = 500
        p.volume_max = 300        
        self.assertIsNotNone(p.get_contract_pricing_errors(350, 1000))

        p = Pricing()
        p.price_base = 500
        p.collateral_max = 300        
        self.assertIsNotNone(p.get_contract_pricing_errors(350, 1000))

        p = Pricing()
        p.price_base = 500
        p.collateral_min = 300        
        self.assertIsNotNone(p.get_contract_pricing_errors(350, 200))

        p = Pricing()
        p.price_base = 500        
        self.assertIsNotNone(p.get_contract_pricing_errors(350, 200, 400))
        
        p = Pricing()
        p.price_base = 500
        with self.assertRaises(ValueError):            
            p.get_contract_pricing_errors(-5, 0)

        with self.assertRaises(ValueError):            
            p.get_contract_pricing_errors(50, -5)

        with self.assertRaises(ValueError):            
            p.get_contract_pricing_errors(50, 5, -5)
        
        p = Pricing()
        with self.assertRaises(ValidationError):
            p.get_calculated_price(1, 1)
