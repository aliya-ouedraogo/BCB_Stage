from django.urls import path
from . import views

app_name = 'appStage'

urlpatterns = [
    path('', views.onboarding, name='home'),
    path('onboarding/', views.onboarding, name='onboarding'),

    path('login/', views.ConnexionView.as_view(), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.deconnexion, name='logout'),

    path('rh/', views.dashboard_rh, name='dashboard_rh'),
    path('tuteur/', views.dashboard_tuteur, name='dashboard_tuteur'),
    path('stagiaire/', views.dashboard_stagiaire, name='dashboard_stagiaire'),
     path('stagiaire/pointer/', views.pointer_presence, name='pointer_presence'),
]
