import logging
import os

def get_swagger_spec_path() -> str:
    """returns the path to the current swagger spec file"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        'swagger.json'
    )

def makeLoggerPrefix(tag: str):
    """creates a function to add logger prefix"""
    return lambda text : '{}: {}'.format(tag, text)


class LoggerAddTag(logging.LoggerAdapter):
    """add custom tag to a logger"""
    def __init__(self, logger, prefix):
        super(LoggerAddTag, self).__init__(logger, {})
        self.prefix = prefix

    def process(self, msg, kwargs):
        return '[%s] %s' % (self.prefix, msg), kwargs

