from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls
from .app_settings import FREIGHT_APP_NAME
from .models import Contract


class ExampleMenuItem(MenuItemHook):
    """This class ensures only authorized users will see the menu entry"""

    def __init__(self):
        # setup menu entry for sidebar
        MenuItemHook.__init__(
            self,
            FREIGHT_APP_NAME,
            "fas fa-truck fa-fw",
            "freight:index",
            navactive=["freight:"],
        )

    def render(self, request):
        if request.user.has_perm("freight.basic_access"):
            if request.user.has_perm("freight.view_contracts"):
                app_count = Contract.objects.all().pending_count()
                self.count = app_count if app_count and app_count > 0 else None

            return MenuItemHook.render(self, request)

        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return ExampleMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "freight", r"^freight/")
