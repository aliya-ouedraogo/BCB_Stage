from django.urls import path
from . import views

app_name = 'appStage'

urlpatterns = [
    path('', views.onboarding, name='home'),
    path('onboarding/', views.onboarding, name='onboarding'),

    path('login/', views.ConnexionView.as_view(), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.deconnexion, name='logout'),

    # --- RH ---
    path('rh/', views.dashboard_rh, name='dashboard_rh'),
    path('rh/stagiaires/', views.liste_stagiaires, name='liste_stagiaires'),
    path('rh/candidatures/', views.candidatures, name='candidatures'),
    path('rh/candidatures/<int:candidature_id>/accepter/', views.accepter_candidature, name='accepter_candidature'),
    path('rh/candidatures/<int:candidature_id>/refuser/', views.refuser_candidature, name='refuser_candidature'),

    # --- Maître de stage ---
    path('tuteur/', views.dashboard_tuteur, name='dashboard_tuteur'),
    path('tuteur/mes-stagiaires/', views.mes_stagiaires, name='mes_stagiaires'),
    path('tuteur/evaluer/<int:stage_id>/', views.evaluer, name='evaluer'),
    path('tuteur/demande/<int:demande_id>/<str:reponse>/', views.repondre_demande_encadrement, name='repondre_demande_encadrement'),

    # --- Fiche stagiaire (partagée tuteur + RH) ---
    path('stage/<int:stage_id>/', views.fiche_stagiaire, name='fiche_stagiaire'),

    # --- Stagiaire ---
    path('stagiaire/', views.dashboard_stagiaire, name='dashboard_stagiaire'),
    path('stagiaire/missions/', views.mes_missions, name='mes_missions'),
    path('stagiaire/documents/', views.mes_documents, name='mes_documents'),
    path('stagiaire/choisir-tuteur/', views.choisir_tuteur, name='choisir_tuteur'),
    path('stagiaire/pointer/', views.pointer_presence, name='pointer_presence'),
    path('stagiaire/mission/<int:mission_id>/avancer/', views.avancer_mission, name='avancer_mission'),

    # --- Commun ---
    path('parametres/', views.parametres, name='parametres'),
]
