from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Allow access to platform admins and super admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.platform_role in ('admin', 'super_admin')
        )


class IsSuperAdmin(BasePermission):
    """Allow access to platform super admins only."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.platform_role == 'super_admin'
        )
