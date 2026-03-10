from main.models import User


class RolePermissionService:

    @staticmethod
    def is_admin(user: User) -> bool:
        return user.role == User.RoleChoices.ADMIN
