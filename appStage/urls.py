from django.urls import path
from . import views

app_name = 'appStage'

urlpatterns = [
    path('', views.onboarding, name='home'),
    path('onboarding/', views.onboarding, name='onboarding'),

    path('login/', views.ConnexionView.as_view(), name='login'),
    path('candidature/', views.candidature_publique, name='candidature_publique'),
    path('activer/<str:uidb64>/<str:token>/', views.activer_compte, name='activer_compte'),
    path('logout/', views.deconnexion, name='logout'),

    # --- RH ---
    path('rh/', views.dashboard_rh, name='dashboard_rh'),
    path('rh/stagiaires/', views.liste_stagiaires, name='liste_stagiaires'),
    path('rh/stagiaires/export/', views.exporter_stagiaires_csv, name='exporter_stagiaires_csv'),
    path('rh/affecter-service/', views.affecter_service, name='affecter_service'),
    path('rh/candidatures/', views.candidatures, name='candidatures'),
    path('rh/candidatures/export/', views.exporter_candidatures_csv, name='exporter_candidatures_csv'),
    path('rh/candidatures/<int:candidature_id>/accepter/', views.accepter_candidature, name='accepter_candidature'),
    path('rh/candidatures/<int:candidature_id>/refuser/', views.refuser_candidature, name='refuser_candidature'),
    path('rh/candidatures/<int:candidature_id>/supprimer/', views.supprimer_candidature, name='supprimer_candidature'),
    path('rh/documents/', views.documents_recus_rh, name='documents_recus_rh'),
    path('rh/documents/envoyer/<int:stage_id>/', views.envoyer_document_rh, name='envoyer_document_rh'),
    path('rh/tuteurs/', views.gestion_tuteurs, name='gestion_tuteurs'),
    path('rh/tuteurs/export/', views.exporter_tuteurs_csv, name='exporter_tuteurs_csv'),
    path('rh/tuteurs/<int:tuteur_id>/supprimer/', views.supprimer_tuteur, name='supprimer_tuteur'),
    path('rh/directeurs/', views.gestion_directeurs, name='gestion_directeurs'),
    path('rh/directeurs/export/', views.exporter_directeurs_csv, name='exporter_directeurs_csv'),
    path('rh/directeurs/<int:directeur_id>/supprimer/', views.supprimer_directeur, name='supprimer_directeur'),
    path('rh/services/', views.gestion_departements, name='gestion_departements'),
    path('rh/services/export/', views.exporter_departements_csv, name='exporter_departements_csv'),
    path('rh/services/<int:departement_id>/supprimer/', views.supprimer_departement, name='supprimer_departement'),

    # --- Directeur de service ---
    path('directeur/', views.dashboard_directeur, name='dashboard_directeur'),
    path('directeur/affecter-maitre-stage/', views.affecter_maitre_stage, name='affecter_maitre_stage'),
    path('directeur/documents-recus/', views.documents_recus_directeur, name='documents_recus_directeur'),

    # --- Maître de stage ---
    path('tuteur/', views.dashboard_tuteur, name='dashboard_tuteur'),
    path('tuteur/mes-stagiaires/', views.mes_stagiaires, name='mes_stagiaires'),
    path('tuteur/documents-recus/', views.documents_recus, name='documents_recus'),
    path('tuteur/assigner-mission/', views.assigner_mission, name='assigner_mission'),
    path('tuteur/evaluer/<int:stage_id>/', views.evaluer, name='evaluer'),
    path('tuteur/demande/<int:demande_id>/<str:reponse>/', views.repondre_demande_encadrement, name='repondre_demande_encadrement'),

    # --- Fiche stagiaire (partagée tuteur + RH) ---
    path('stage/<int:stage_id>/', views.fiche_stagiaire, name='fiche_stagiaire'),

    # --- Stagiaire ---
    path('stagiaire/', views.dashboard_stagiaire, name='dashboard_stagiaire'),
    path('stagiaire/missions/', views.mes_missions, name='mes_missions'),
    path('stagiaire/documents/', views.mes_documents, name='mes_documents'),
    path('stagiaire/documents/soumettre/', views.soumettre_document, name='soumettre_document'),
    path('stagiaire/documents/<int:document_id>/modifier/', views.modifier_document, name='modifier_document'),
    path('documents/<int:document_id>/signer/', views.signer_document, name='signer_document'),
    path('stagiaire/pointer/', views.pointer_presence, name='pointer_presence'),
    path('presence/<int:presence_id>/<str:action>/', views.confirmer_presence, name='confirmer_presence'),
    path('stage/<int:stage_id>/presence/confirmer-tout/', views.confirmer_semaine_presence, name='confirmer_semaine_presence'),
    path('stagiaire/mission/<int:mission_id>/avancer/', views.avancer_mission, name='avancer_mission'),

    # --- Notifications (communes) ---
    path('notifications/<int:notification_id>/lue/', views.marquer_notification_lue, name='marquer_notification_lue'),
    path('notifications/tout-marquer-lu/', views.marquer_toutes_notifications_lues, name='marquer_toutes_notifications_lues'),

    # --- Commun ---
    path('parametres/', views.parametres, name='parametres'),
]
