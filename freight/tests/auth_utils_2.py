from django.contrib.auth.models import User, Permission

from allianceauth.tests.auth_utils import AuthUtils


class AuthUtils2:
    
    @staticmethod
    def add_permission_to_user_by_name(
        permission_name, user, disconnect_signals=True
    ):
        """adds permission to user

        permission_name: Permission in format 'app_label.codename'

        user: user object

        disconnect_signals: whether to disconnect all signals
        """
        if disconnect_signals:
            AuthUtils.disconnect_signals()
        
        permission_parts = permission_name.split('.')
        if len(permission_parts) != 2:
            raise ValueError('Invalid format for permission name')

        p = Permission.objects.get(
            content_type__app_label=permission_parts[0],
            codename=permission_parts[1],
        )
        user.user_permissions.add(p)
        user = User.objects.get(pk=user.pk)

        if disconnect_signals:
            AuthUtils.connect_signals()
