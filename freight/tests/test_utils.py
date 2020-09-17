from datetime import timedelta
from unittest.mock import Mock, patch

import requests

from django.test import TestCase
from django.utils import translation
from django.utils.html import mark_safe

from ..utils import (
    clean_setting,
    messages_plus,
    chunks,
    timeuntil_str,
    NoSocketsTestCase,
    SocketAccessError,
    app_labels,
    add_no_wrap_html,
    yesno_str,
    create_bs_button_html,
    create_bs_glyph_html,
    create_link_html,
    add_bs_label_html,
    get_site_base_url,
)
from ..utils import set_test_logger


MODULE_PATH = "freight.utils"
logger = set_test_logger(MODULE_PATH, __file__)


class TestMessagePlus(TestCase):
    @patch(MODULE_PATH + ".messages")
    def test_valid_call(self, mock_messages):
        messages_plus.debug(Mock(), "Test Message")
        self.assertTrue(mock_messages.debug.called)
        call_args_list = mock_messages.debug.call_args_list
        args, kwargs = call_args_list[0]
        self.assertEqual(
            args[1],
            '<span class="glyphicon glyphicon-eye-open" '
            'aria-hidden="true"></span>&nbsp;&nbsp;'
            "Test Message",
        )

    def test_invalid_level(self):
        with self.assertRaises(ValueError):
            messages_plus._add_messages_icon(987, "Test Message")

    @patch(MODULE_PATH + ".messages")
    def test_all_levels(self, mock_messages):
        text = "Test Message"
        messages_plus.error(Mock(), text)
        self.assertTrue(mock_messages.error.called)

        messages_plus.debug(Mock(), text)
        self.assertTrue(mock_messages.debug.called)

        messages_plus.info(Mock(), text)
        self.assertTrue(mock_messages.info.called)

        messages_plus.success(Mock(), text)
        self.assertTrue(mock_messages.success.called)

        messages_plus.warning(Mock(), text)
        self.assertTrue(mock_messages.warning.called)


class TestChunks(TestCase):
    def test_chunks(self):
        a0 = [1, 2, 3, 4, 5, 6]
        a1 = list(chunks(a0, 2))
        self.assertListEqual(a1, [[1, 2], [3, 4], [5, 6]])


class TestCleanSetting(TestCase):
    @patch(MODULE_PATH + ".settings")
    def test_default_if_not_set(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = Mock(spec=None)
        result = clean_setting(
            "TEST_SETTING_DUMMY",
            False,
        )
        self.assertEqual(result, False)

    @patch(MODULE_PATH + ".settings")
    def test_default_if_not_set_for_none(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = Mock(spec=None)
        result = clean_setting("TEST_SETTING_DUMMY", None, required_type=int)
        self.assertEqual(result, None)

    @patch(MODULE_PATH + ".settings")
    def test_true_stays_true(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = True
        result = clean_setting(
            "TEST_SETTING_DUMMY",
            False,
        )
        self.assertEqual(result, True)

    @patch(MODULE_PATH + ".settings")
    def test_false_stays_false(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = False
        result = clean_setting("TEST_SETTING_DUMMY", False)
        self.assertEqual(result, False)

    @patch(MODULE_PATH + ".settings")
    def test_default_for_invalid_type_bool(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = "invalid type"
        result = clean_setting("TEST_SETTING_DUMMY", False)
        self.assertEqual(result, False)

    @patch(MODULE_PATH + ".settings")
    def test_default_for_invalid_type_int(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = "invalid type"
        result = clean_setting("TEST_SETTING_DUMMY", 50)
        self.assertEqual(result, 50)

    @patch(MODULE_PATH + ".settings")
    def test_default_if_below_minimum_1(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = -5
        result = clean_setting("TEST_SETTING_DUMMY", default_value=50)
        self.assertEqual(result, 50)

    @patch(MODULE_PATH + ".settings")
    def test_default_if_below_minimum_2(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = -50
        result = clean_setting("TEST_SETTING_DUMMY", default_value=50, min_value=-10)
        self.assertEqual(result, 50)

    @patch(MODULE_PATH + ".settings")
    def test_default_for_invalid_type_int_2(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = 1000
        result = clean_setting("TEST_SETTING_DUMMY", default_value=50, max_value=100)
        self.assertEqual(result, 50)

    @patch(MODULE_PATH + ".settings")
    def test_default_is_none_needs_required_type(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = "invalid type"
        with self.assertRaises(ValueError):
            clean_setting("TEST_SETTING_DUMMY", default_value=None)

    @patch(MODULE_PATH + ".settings")
    def test_when_value_in_choices_return_it(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = "bravo"
        result = clean_setting(
            "TEST_SETTING_DUMMY", default_value="alpha", choices=["alpha", "bravo"]
        )
        self.assertEqual(result, "bravo")

    @patch(MODULE_PATH + ".settings")
    def test_when_value_not_in_choices_return_default(self, mock_settings):
        mock_settings.TEST_SETTING_DUMMY = "charlie"
        result = clean_setting(
            "TEST_SETTING_DUMMY", default_value="alpha", choices=["alpha", "bravo"]
        )
        self.assertEqual(result, "alpha")


class TestTimeUntil(TestCase):
    def test_timeuntil(self):
        duration = timedelta(days=365 + 30 * 4 + 5, seconds=3600 * 14 + 60 * 33 + 10)
        expected = "1y 4mt 5d 14h 33m 10s"
        self.assertEqual(timeuntil_str(duration), expected)

        duration = timedelta(days=2, seconds=3600 * 14 + 60 * 33 + 10)
        expected = "2d 14h 33m 10s"
        self.assertEqual(timeuntil_str(duration), expected)

        duration = timedelta(days=2, seconds=3600 * 14 + 60 * 33 + 10)
        expected = "2d 14h 33m 10s"
        self.assertEqual(timeuntil_str(duration), expected)

        duration = timedelta(days=0, seconds=60 * 33 + 10)
        expected = "0h 33m 10s"
        self.assertEqual(timeuntil_str(duration), expected)

        duration = timedelta(days=0, seconds=10)
        expected = "0h 0m 10s"
        self.assertEqual(timeuntil_str(duration), expected)

        duration = timedelta(days=-10, seconds=-20)
        expected = ""
        self.assertEqual(timeuntil_str(duration), expected)


class TestNoSocketsTestCase(NoSocketsTestCase):
    def test_raises_exception_on_attempted_network_access(self):

        with self.assertRaises(SocketAccessError):
            requests.get("https://www.google.com")


class TestAppLabel(TestCase):
    def test_returns_set_of_app_labels(self):
        labels = app_labels()
        for label in ["authentication", "groupmanagement", "eveonline"]:
            self.assertIn(label, labels)


class TestHtmlHelper(TestCase):
    def test_add_no_wrap_html(self):
        expected = '<span style="white-space: nowrap;">Dummy</span>'
        self.assertEqual(add_no_wrap_html("Dummy"), expected)

    def test_yesno_str(self):
        with translation.override("en"):
            self.assertEqual(yesno_str(True), "yes")
            self.assertEqual(yesno_str(False), "no")
            self.assertEqual(yesno_str(None), "no")
            self.assertEqual(yesno_str(123), "no")
            self.assertEqual(yesno_str("xxxx"), "no")

    def test_add_bs_label_html(self):
        expected = '<div class="label label-danger">Dummy</div>'
        self.assertEqual(add_bs_label_html("Dummy", "danger"), expected)

    def test_create_link_html_default(self):
        expected = (
            '<a href="https://www.example.com" target="_blank">' "Example Link</a>"
        )
        self.assertEqual(
            create_link_html("https://www.example.com", "Example Link"), expected
        )

    def test_create_link_html(self):
        expected = '<a href="https://www.example.com">Example Link</a>'
        self.assertEqual(
            create_link_html("https://www.example.com", "Example Link", False), expected
        )
        expected = (
            '<a href="https://www.example.com">' "<strong>Example Link</strong></a>"
        )
        self.assertEqual(
            create_link_html(
                "https://www.example.com",
                mark_safe("<strong>Example Link</strong>"),
                False,
            ),
            expected,
        )

    def test_create_bs_glyph_html(self):
        expected = '<span class="glyphicon glyphicon-example"></span>'
        self.assertEqual(create_bs_glyph_html("example"), expected)

    def test_create_bs_button_html_default(self):
        expected = (
            '<a href="https://www.example.com" class="btn btn-info">'
            '<span class="glyphicon glyphicon-example"></span></a>'
        )
        self.assertEqual(
            create_bs_button_html("https://www.example.com", "example", "info"),
            expected,
        )

    def test_create_bs_button_html_disabled(self):
        expected = (
            '<a href="https://www.example.com" class="btn btn-info"'
            ' disabled="disabled">'
            '<span class="glyphicon glyphicon-example"></span></a>'
        )
        self.assertEqual(
            create_bs_button_html("https://www.example.com", "example", "info", True),
            expected,
        )


class TestGetSiteBaseUrl(NoSocketsTestCase):
    @patch(
        MODULE_PATH + ".settings.ESI_SSO_CALLBACK_URL",
        "https://www.mysite.com/sso/callback",
    )
    def test_return_url_if_url_defined_and_valid(self):
        expected = "https://www.mysite.com"
        self.assertEqual(get_site_base_url(), expected)

    @patch(
        MODULE_PATH + ".settings.ESI_SSO_CALLBACK_URL",
        "https://www.mysite.com/not-valid/",
    )
    def test_return_dummy_if_url_defined_but_not_valid(self):
        expected = "http://www.example.com"
        self.assertEqual(get_site_base_url(), expected)

    @patch(MODULE_PATH + ".settings")
    def test_return_dummy_if_url_not_defined(self, mock_settings):
        delattr(mock_settings, "ESI_SSO_CALLBACK_URL")
        expected = "http://www.example.com"
        self.assertEqual(get_site_base_url(), expected)
