def nav_items(request):
    """
    Fournit la liste des liens de navigation adaptés au rôle de l'utilisateur
    connecté. Utilisé à la fois par la sidebar desktop et la barre de
    navigation mobile dans base_dashboard.html, une seule source de vérité,
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
            {'label': 'Affectations', 'icon': 'user-plus', 'url_name': 'appStage:mes_affectations', 'badge': _nb_affectations_en_attente(request.user)},
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
            {'label': 'Entretiens', 'icon': 'calendar-clock', 'url_name': 'appStage:planifier_stages', 'badge': _nb_candidatures_en_entretien()},
            {'label': 'Stagiaires', 'icon': 'users', 'url_name': 'appStage:liste_stagiaires'},
            {'label': 'Affectation', 'icon': 'building-2', 'url_name': 'appStage:affecter_service', 'badge': _nb_stagiaires_a_affecter()},
            {'label': 'Maîtres de Stage', 'icon': 'user-check', 'url_name': 'appStage:gestion_tuteurs'},
            {'label': 'Directeurs', 'icon': 'shield', 'url_name': 'appStage:gestion_directeurs'},
            {'label': 'Services', 'icon': 'building', 'url_name': 'appStage:gestion_departements'},
            {'label': 'Documents Reçus', 'icon': 'inbox', 'url_name': 'appStage:documents_recus_rh'},
            {'label': 'Paramètres', 'icon': 'settings', 'url_name': 'appStage:parametres'},
        ],
    }

    return {
        'nav_items': items_par_role.get(request.user.role, []),
    }


def _nb_candidatures_en_attente():
    """Nombre de candidatures pas encore traitées, pour le badge de la sidebar RH."""
    from .models import Candidature
    return Candidature.objects.filter(statut=Candidature.Statut.EN_ATTENTE).count()


def _nb_candidatures_en_entretien():
    """Nombre de candidats dont l'entretien est programmé et la période de stage reste à renseigner, pour le badge Entretiens."""
    from .models import Candidature
    return Candidature.objects.filter(statut=Candidature.Statut.ENTRETIEN).count()


def _nb_stagiaires_a_affecter():
    """Nombre de stagiaires acceptés qui n'ont pas encore de service, pour le badge Affectation."""
    from .models import Stage
    return Stage.objects.filter(departement__isnull=True).exclude(statut=Stage.Statut.RESILIE).count()


def _nb_affectations_en_attente(user):
    """Nombre de propositions d'encadrement en attente de réponse pour ce maître de stage, pour le badge Affectations."""
    from .models import DemandeEncadrement
    profil = getattr(user, 'profil_maitre_stage', None)
    if not profil:
        return 0
    return DemandeEncadrement.objects.filter(
        maitre_de_stage_demande=profil, statut=DemandeEncadrement.Statut.EN_ATTENTE,
    ).count()
