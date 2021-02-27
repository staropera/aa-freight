from esi.clients import EsiClientProvider

from . import __version__


esi = EsiClientProvider(app_info_text=f"aa-freight v{__version__}")
