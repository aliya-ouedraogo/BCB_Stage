def nav_items(request):
    """
    Fournit la liste des liens de navigation adaptés au rôle de l'utilisateur
    connecté. Utilisé à la fois par la sidebar desktop et la barre de
    navigation mobile dans base_dashboard.html — une seule source de vérité,
    donc impossible d'avoir des liens différents/incohérents selon la page.
    """
    if not request.user.is_authenticated or not getattr(request.user, 'role', None):
        return {}

    items_par_role = {
        'STAGIAIRE': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_stagiaire'},
            {'label': 'Mes Missions', 'icon': 'target', 'url_name': 'appStage:mes_missions'},
            {'label': 'Mes Documents', 'icon': 'file-text', 'url_name': 'appStage:mes_documents'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'MAITRE_STAGE': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_tuteur'},
            {'label': 'Mes Stagiaires', 'icon': 'users', 'url_name': 'appStage:mes_stagiaires'},
            {'label': 'Documents Reçus', 'icon': 'inbox', 'url_name': 'appStage:documents_recus'},
            {'label': 'Missions', 'icon': 'clipboard-list', 'url_name': 'appStage:assigner_mission'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'DIRECTEUR': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_directeur'},
            {'label': 'Encadrement', 'icon': 'user-check', 'url_name': 'appStage:affecter_maitre_stage'},
            {'label': 'Documents', 'icon': 'inbox', 'url_name': 'appStage:documents_recus_directeur'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'RH': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_rh'},
            {'label': 'Candidatures', 'icon': 'user-plus', 'url_name': 'appStage:candidatures', 'badge': _nb_candidatures_en_attente()},
            {'label': 'Stagiaires', 'icon': 'users', 'url_name': 'appStage:liste_stagiaires'},
            {'label': 'Affectation', 'icon': 'building-2', 'url_name': 'appStage:affecter_service'},
            {'label': 'Maîtres de Stage', 'icon': 'user-check', 'url_name': 'appStage:gestion_tuteurs'},
            {'label': 'Directeurs', 'icon': 'shield', 'url_name': 'appStage:gestion_directeurs'},
            {'label': 'Services', 'icon': 'building', 'url_name': 'appStage:gestion_departements'},
            {'label': 'Documents Reçus', 'icon': 'inbox', 'url_name': 'appStage:documents_recus_rh'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
    }

    return {'nav_items': items_par_role.get(request.user.role, [])}


def _nb_candidatures_en_attente():
    """Nombre de candidatures pas encore traitées, pour le badge de la sidebar RH."""
    from .models import Candidature
    return Candidature.objects.filter(statut=Candidature.Statut.EN_ATTENTE).count()
