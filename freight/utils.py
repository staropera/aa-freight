import logging
import os

from django.utils.html import mark_safe
from django.contrib.messages.constants import *
from django.contrib import messages


# Format for output of datetime for this app
DATETIME_FORMAT = '%Y-%m-%d %H:%M'


def get_swagger_spec_path() -> str:
    """returns the path to the current swagger spec file"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        'swagger.json'
    )


def make_logger_prefix(tag: str):
    """creates a function to add logger prefix"""
    return lambda text : '{}: {}'.format(tag, text)


class LoggerAddTag(logging.LoggerAdapter):
    """add custom tag to a logger"""
    def __init__(self, logger, prefix):
        super(LoggerAddTag, self).__init__(logger, {})
        self.prefix = prefix

    def process(self, msg, kwargs):
        return '[%s] %s' % (self.prefix, msg), kwargs



class messages_plus():
    """Pendant to Django messages adding level icons and HTML support
    
    Careful: Use with safe strings only
    """

    @classmethod
    def add_messages_icon(cls,level, message):
        """Adds an level based icon to Django messages"""
        glyph_map = {
            DEBUG: 'eye-open',
            INFO: 'info-sign',
            SUCCESS: 'ok-sign',
            WARNING: 'exclamation-sign',
            ERROR: 'alert',
        }
        if level in glyph_map:
            glyph = glyph_map[level]
        else:
            glyph = glyph_map[INFO]

        message = ('<span class="glyphicon glyphicon-{}" '.format(glyph)
            + 'aria-hidden="true"></span>&nbsp;&nbsp;' 
            + message)
        return mark_safe(message)

    @classmethod
    def debug(cls, request, message, extra_tags='', fail_silently=False):
        messages.debug(
            request, 
            cls.add_messages_icon(DEBUG, message), 
            extra_tags, 
            fail_silently
        )

    @classmethod
    def info(cls, request, message, extra_tags='', fail_silently=False):
        messages.info(
            request, 
            cls.add_messages_icon(INFO, message), 
            extra_tags, 
            fail_silently
        )
    @classmethod
    def success(cls, request, message, extra_tags='', fail_silently=False):
        messages.success(
            request, 
            cls.add_messages_icon(SUCCESS, message), 
            extra_tags, 
            fail_silently
        )
    
    @classmethod
    def warning(cls, request, message, extra_tags='', fail_silently=False):
        messages.warning(
            request, 
            cls.add_messages_icon(WARNING, message), 
            extra_tags, 
            fail_silently
        )
    
    @classmethod
    def error(cls, request, message, extra_tags='', fail_silently=False):
        messages.error(
            request, 
            cls.add_messages_icon(ERROR, message), 
            extra_tags, 
            fail_silently
        )
