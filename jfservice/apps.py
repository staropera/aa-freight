from django.apps import AppConfig
from . import __version__

class JfServiceConfig(AppConfig):
    name = 'jfservice'
    label = 'jfservice'
    verbose_name = 'JF Service v{}'.format(__version__)
