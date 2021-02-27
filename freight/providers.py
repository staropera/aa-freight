import logging

from app_utils.logging import LoggerAddTag
from esi.clients import EsiClientProvider

from . import __title__, __version__


logger = LoggerAddTag(logging.getLogger(__name__), __title__)
esi = EsiClientProvider(app_info_text=f"aa-freight v{__version__}")
