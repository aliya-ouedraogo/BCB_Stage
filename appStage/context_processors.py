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
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
        'RH': [
            {'label': 'Tableau de bord', 'icon': 'layout-dashboard', 'url_name': 'appStage:dashboard_rh'},
            {'label': 'Stagiaires', 'icon': 'users', 'url_name': 'appStage:liste_stagiaires'},
            {'label': 'Candidatures', 'icon': 'user-plus', 'url_name': 'appStage:candidatures'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
    }

    return {'nav_items': items_par_role.get(request.user.role, [])}
