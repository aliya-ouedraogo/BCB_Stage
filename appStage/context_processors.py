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
            {'label': 'Assigner une Mission', 'icon': 'clipboard-list', 'url_name': 'appStage:assigner_mission'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'DIRECTEUR': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_directeur'},
            {'label': 'Affecter un Maître de Stage', 'icon': 'user-check', 'url_name': 'appStage:affecter_maitre_stage'},
            {'label': 'Documents', 'icon': 'inbox', 'url_name': 'appStage:documents_recus_directeur'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'RH': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_rh'},
            {'label': 'Stagiaires', 'icon': 'users', 'url_name': 'appStage:liste_stagiaires'},
            {'label': 'Services', 'icon': 'building', 'url_name': 'appStage:gestion_departements'},
            {'label': 'Affecter un Service', 'icon': 'building-2', 'url_name': 'appStage:affecter_service'},
            {'label': 'Candidatures', 'icon': 'user-plus', 'url_name': 'appStage:candidatures'},
            {'label': 'Maîtres de Stage', 'icon': 'user-check', 'url_name': 'appStage:gestion_tuteurs'},
            {'label': 'Directeurs', 'icon': 'shield', 'url_name': 'appStage:gestion_directeurs'},
            {'label': 'Documents Reçus', 'icon': 'inbox', 'url_name': 'appStage:documents_recus_rh'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
    }

    return {'nav_items': items_par_role.get(request.user.role, [])}


def notifications_cloche(request):
    """
    Fournit les notifications récentes (et le nombre de non-lues) pour la
    cloche affichée dans le topbar de base_dashboard.html, pour les 4 rôles.
    """
    if not request.user.is_authenticated or not getattr(request.user, 'role', None):
        return {}

    qs = request.user.notifications.all()
    return {
        'notifications_recentes': qs[:8],
        'notifications_non_lues': qs.filter(lu=False).count(),
    }
