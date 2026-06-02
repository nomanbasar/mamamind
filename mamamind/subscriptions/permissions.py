from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminUserRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_staff or user.is_superuser:
            return True

        if hasattr(user, "role") and user.role == "admin":
            return True

        return False


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_staff or user.is_superuser:
            return True

        if hasattr(user, "role") and user.role == "admin":
            return True

        return False