from django.apps import AppConfig
from . import __version__

class JfServiceConfig(AppConfig):
    name = 'jfservice'
    label = 'jfservice'
    verbose_name = 'Freight Shipping v{}'.format(__version__)
