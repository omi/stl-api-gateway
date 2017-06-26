from rest_framework import permissions


class IsPostAuthenticatedOrReadonly(permissions.BasePermission):
    def has_permission(self, request, view):
        if view.action == 'create':
            if request.user.is_authenticated():
                return True
            return False
        return request.method in permissions.SAFE_METHODS
