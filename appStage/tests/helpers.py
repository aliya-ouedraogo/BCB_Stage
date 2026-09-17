"""
Utilitaires communs aux tests de l'app appStage.

Point important : appStage.models.envoyer_email_arriere_plan() envoie les
emails dans un thread daemon séparé (pour ne jamais bloquer/faire échouer
une action métier à cause d'un souci SMTP). Sans précaution, un test qui
vérifie mail.outbox juste après avoir appelé une méthode métier serait
non déterministe (le thread peut ne pas avoir fini d'écrire dans
mail.outbox au moment de l'assertion).

SynchronousTestCase remplace threading.Thread par une fausse version qui
exécute la cible immédiatement, de façon synchrone, dans le thread du
test. Ainsi mail.outbox est à jour dès le retour de l'appel qui a
déclenché l'email, sans sleep ni polling.
"""
from unittest import mock

from django.test import TestCase

from appStage import models as appStage_models


class ThreadImmediat:
    """
    Remplace threading.Thread pendant les tests : exécute la cible tout de
    suite au lieu de démarrer un vrai thread. Signature compatible avec
    threading.Thread(target=..., daemon=...) tel qu'utilisé par
    envoyer_email_arriere_plan, y compris les méthodes start()/join()
    attendues par l'appelant.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        pass


class SynchronousTestCase(TestCase):
    """
    TestCase de base qui rend synchrones tous les envois d'email passant
    par envoyer_email_arriere_plan(), pour que mail.outbox soit fiable
    dans les assertions. À utiliser à la place de django.test.TestCase
    pour tout test qui déclenche une action envoyant un email.
    """

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(appStage_models.threading, 'Thread', ThreadImmediat)
        patcher.start()
        self.addCleanup(patcher.stop)


# ---------------------------------------------------------------------
# Fabriques de données de test — un seul endroit à mettre à jour si les
# champs obligatoires des modèles changent.
# ---------------------------------------------------------------------

def creer_rh(username='rh1', **kwargs):
    from appStage.models import User
    user = User.objects.create_user(
        username=username, email=f'{username}@bcbstageflow.test',
        password='motdepasse123', role=User.Role.RH,
        first_name='Rita', last_name='Hériaux', **kwargs,
    )
    # Le profil est déjà créé automatiquement par le signal post_save
    # (voir appStage/signals.py) dès que le User est sauvegardé avec ce
    # rôle : le récupérer plutôt que le recréer évite un doublon (erreur
    # d'intégrité sur la contrainte unique du OneToOneField).
    return user.profil_rh


def creer_directeur(username='directeur1', departement=None, **kwargs):
    from appStage.models import User
    user = User.objects.create_user(
        username=username, email=f'{username}@bcbstageflow.test',
        password='motdepasse123', role=User.Role.DIRECTEUR,
        first_name='Didier', last_name='Écteur', **kwargs,
    )
    profil = user.profil_directeur
    if departement is not None:
        departement.directeur = profil
        departement.save(update_fields=['directeur'])
    return profil


def creer_tuteur(username='tuteur1', **kwargs):
    from appStage.models import User
    user = User.objects.create_user(
        username=username, email=f'{username}@bcbstageflow.test',
        password='motdepasse123', role=User.Role.MAITRE_STAGE,
        first_name='Tania', last_name='Tuteur', **kwargs,
    )
    return user.profil_maitre_stage


def creer_stagiaire_direct(username='stagiaire1', **kwargs):
    """Crée un stagiaire sans passer par le parcours Candidature (pour des tests ciblés)."""
    from appStage.models import ProfilStagiaire, User
    user = User.objects.create_user(
        username=username, email=f'{username}@bcbstageflow.test',
        password='motdepasse123', role=User.Role.STAGIAIRE,
        first_name='Sara', last_name='Giaire', **kwargs,
    )
    return ProfilStagiaire.objects.create(user=user)


def creer_departement(nom='Développement Web', **kwargs):
    from appStage.models import Departement
    return Departement.objects.create(nom=nom, **kwargs)


def creer_candidature(**kwargs):
    from appStage.models import Candidature
    defaults = dict(
        nom_complet='Awa Compaoré',
        email='awa.compaore@example.com',
        telephone='+22670000001',
        poste_souhaite='Stagiaire Développeuse',
        filiere='Informatique',
        avec_soutenance_souhaite=True,
    )
    defaults.update(kwargs)
    return Candidature.objects.create(**defaults)


def creer_stage(stagiaire, departement=None, **kwargs):
    from appStage.models import Stage
    import datetime
    from django.utils import timezone
    defaults = dict(
        intitule_poste='Stagiaire Développeur',
        date_debut=timezone.now().date(),
        date_fin=timezone.now().date() + datetime.timedelta(days=90),
        statut=Stage.Statut.A_VENIR,
    )
    defaults.update(kwargs)
    return Stage.objects.create(stagiaire=stagiaire, departement=departement, **defaults)
