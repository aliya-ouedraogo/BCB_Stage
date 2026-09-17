import datetime

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from appStage.models import Candidature, DemandeEncadrement, Stage
from appStage.tests.helpers import (
    SynchronousTestCase,
    creer_candidature,
    creer_departement,
    creer_directeur,
    creer_rh,
    creer_stage,
    creer_stagiaire_direct,
    creer_tuteur,
)


def _badge(nav_items, label):
    for item in nav_items:
        if item['label'] == label:
            return item.get('badge')
    raise AssertionError(f"Aucun item de nav avec le label {label!r} : {nav_items}")


class BadgesRHTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.rh = creer_rh()
        self.client = Client()
        self.client.force_login(self.rh.user)

    def test_badge_candidatures_compte_seulement_en_attente(self):
        creer_candidature(email='a@example.com')
        creer_candidature(email='b@example.com', statut=Candidature.Statut.ENTRETIEN)
        reponse = self.client.get(reverse('appStage:dashboard_rh'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Candidatures'), 1)

    def test_badge_entretiens_compte_les_candidatures_en_entretien(self):
        creer_candidature(email='a@example.com', statut=Candidature.Statut.ENTRETIEN)
        creer_candidature(email='b@example.com', statut=Candidature.Statut.ENTRETIEN)
        creer_candidature(email='c@example.com')  # EN_ATTENTE, ne doit pas compter
        reponse = self.client.get(reverse('appStage:dashboard_rh'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Entretiens'), 2)

    def test_badge_affectation_compte_les_stages_sans_departement(self):
        stagiaire = creer_stagiaire_direct()
        creer_stage(stagiaire, departement=None)
        reponse = self.client.get(reverse('appStage:dashboard_rh'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Affectation'), 1)

    def test_badge_affectation_exclut_les_stages_resilies(self):
        stagiaire = creer_stagiaire_direct()
        creer_stage(stagiaire, departement=None, statut=Stage.Statut.RESILIE)
        reponse = self.client.get(reverse('appStage:dashboard_rh'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Affectation'), 0)


class BadgesMaitreDeStageTests(SynchronousTestCase):
    def test_badge_affectations_compte_les_demandes_en_attente_pour_ce_tuteur_seulement(self):
        departement = creer_departement()
        directeur = creer_directeur(departement=departement)
        tuteur = creer_tuteur()
        autre_tuteur = creer_tuteur(username='autre_tuteur')
        stagiaire = creer_stagiaire_direct()
        stage = creer_stage(stagiaire, departement=departement)

        DemandeEncadrement.objects.create(stage=stage, maitre_de_stage_demande=tuteur, proposee_par=directeur)
        DemandeEncadrement.objects.create(stage=stage, maitre_de_stage_demande=autre_tuteur, proposee_par=directeur)

        client = Client()
        client.force_login(tuteur.user)
        reponse = client.get(reverse('appStage:dashboard_tuteur'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Affectations'), 1)


class BadgesDirecteurTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.departement = creer_departement()
        self.directeur = creer_directeur(departement=self.departement)
        self.client = Client()
        self.client.force_login(self.directeur.user)

    def test_badge_encadrement_compte_les_stagiaires_sans_tuteur_ni_proposition(self):
        stagiaire = creer_stagiaire_direct()
        creer_stage(stagiaire, departement=self.departement, statut=Stage.Statut.EN_COURS)
        reponse = self.client.get(reverse('appStage:dashboard_directeur'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Encadrement'), 1)

    def test_badge_encadrement_exclut_les_stages_avec_proposition_en_cours(self):
        stagiaire = creer_stagiaire_direct()
        stage = creer_stage(stagiaire, departement=self.departement, statut=Stage.Statut.EN_COURS)
        tuteur = creer_tuteur()
        DemandeEncadrement.objects.create(stage=stage, maitre_de_stage_demande=tuteur, proposee_par=self.directeur)

        reponse = self.client.get(reverse('appStage:dashboard_directeur'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Encadrement'), 0)

    def test_badge_encadrement_exclut_les_stages_deja_encadres(self):
        stagiaire = creer_stagiaire_direct()
        tuteur = creer_tuteur()
        creer_stage(
            stagiaire, departement=self.departement,
            statut=Stage.Statut.EN_COURS, maitre_de_stage=tuteur,
        )
        reponse = self.client.get(reverse('appStage:dashboard_directeur'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Encadrement'), 0)

    def test_badge_zero_pour_directeur_sans_departement(self):
        directeur_sans_service = creer_directeur(username='directeur_orphelin')
        client = Client()
        client.force_login(directeur_sans_service.user)
        reponse = client.get(reverse('appStage:dashboard_directeur'))
        self.assertEqual(_badge(reponse.context['nav_items'], 'Encadrement'), 0)
