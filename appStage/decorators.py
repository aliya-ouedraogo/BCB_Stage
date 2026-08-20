from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache


def role_required(*roles_autorises):
    """
    Restreint l'accès à une vue aux utilisateurs connectés dont le rôle
    figure parmi ceux fournis. Redirige vers la connexion si non connecté,
    lève un 403 si le rôle ne correspond pas à l'espace demandé.

    Ajoute aussi never_cache : sans ça, un navigateur peut réafficher une
    page protégée depuis son cache après déconnexion (bouton retour, etc.)
    sans repasser par le serveur — ce qui donnait l'impression qu'on
    restait connecté alors que la session était bien terminée.

    Utilisation :
        @role_required(User.Role.RH)
        def dashboard_rh(request): ...
    """
    def decorateur(vue):
        @never_cache
        @login_required(login_url='appStage:login')
        @wraps(vue)
        def vue_protegee(request, *args, **kwargs):
            if request.user.role not in roles_autorises:
                raise PermissionDenied("Vous n'avez pas accès à cet espace.")
            return vue(request, *args, **kwargs)
        return vue_protegee
    return decorateur
