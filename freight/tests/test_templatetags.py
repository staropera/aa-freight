from django.test import TestCase

from . import set_logger
from ..templatetags.freight_filters import power10, formatnumber


class TestFilters(TestCase):

    @classmethod
    def setUpClass(cls):
        
                
        return super().setUpClass()

    def test_power10(self):
        self.assertEqual(
            power10(1),
            1
        )
        self.assertEqual(
            power10(1000, 3),
            1
        )
        self.assertEqual(
            power10(-1000, 3),
            -1
        )
        self.assertEqual(
            power10(0),
            0            
        )
        self.assertEqual(
            power10(None, 3),
            None
        )
        self.assertEqual(
            power10('xxx', 3),
            None
        )
        self.assertEqual(
            power10('', 3),
            None
        )
        self.assertEqual(
            power10(1000, 'xx'),
            None
        )

    def test_formatnumber(self):
        self.assertEqual(
            formatnumber(1),
            '1.0'
        )
        self.assertEqual(
            formatnumber(1000),
            '1,000.0'
        )
        self.assertEqual(
            formatnumber(1000000),
            '1,000,000.0'
        )
        self.assertEqual(
            formatnumber(1, 0),
            '1'
        )
        self.assertEqual(
            formatnumber(1000, 0),
            '1,000'
        )
        self.assertEqual(
            formatnumber(1000000, 0),
            '1,000,000'
        )
        self.assertEqual(
            formatnumber(-1000),
            '-1,000.0'
        )
        self.assertEqual(
            formatnumber(None),
            None
        )
