from django.urls import path
from . import views

app_name = 'appStage'

urlpatterns = [
     path('', views.onboarding, name='home'), 
    path('onboarding/', views.onboarding, name='onboarding'),
]