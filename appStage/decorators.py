from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles_autorises):
    """
    Restreint l'accès à une vue aux utilisateurs connectés dont le rôle
    figure parmi ceux fournis. Redirige vers la connexion si non connecté,
    lève un 403 si le rôle ne correspond pas à l'espace demandé.

    Utilisation :
        @role_required(User.Role.RH)
        def dashboard_rh(request): ...
    """
    def decorateur(vue):
        @login_required(login_url='appStage:login')
        @wraps(vue)
        def vue_protegee(request, *args, **kwargs):
            if request.user.role not in roles_autorises:
                raise PermissionDenied("Vous n'avez pas accès à cet espace.")
            return vue(request, *args, **kwargs)
        return vue_protegee
    return decorateur
