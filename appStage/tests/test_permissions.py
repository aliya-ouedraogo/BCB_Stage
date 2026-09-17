from django.test import Client
from django.urls import reverse

from appStage.tests.helpers import (
    SynchronousTestCase,
    creer_directeur,
    creer_rh,
    creer_tuteur,
)


class RoleRequiredTests(SynchronousTestCase):
    """
    Vérifie le comportement documenté de role_required : redirection vers
    la connexion si anonyme, 403 si le rôle ne correspond pas, 200 si le
    rôle correspond. Testé sur dashboard_rh, mais le décorateur est
    partagé par toutes les vues protégées.
    """

    def setUp(self):
        super().setUp()
        self.url_dashboard_rh = reverse('appStage:dashboard_rh')

    def test_anonyme_est_redirige_vers_la_connexion(self):
        client = Client()
        reponse = client.get(self.url_dashboard_rh)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse('appStage:login'), reponse.url)

    def test_mauvais_role_recoit_un_403(self):
        tuteur = creer_tuteur()
        client = Client()
        client.force_login(tuteur.user)
        reponse = client.get(self.url_dashboard_rh)
        self.assertEqual(reponse.status_code, 403)

    def test_bon_role_accede_normalement(self):
        rh = creer_rh()
        client = Client()
        client.force_login(rh.user)
        reponse = client.get(self.url_dashboard_rh)
        self.assertEqual(reponse.status_code, 200)

    def test_directeur_sans_departement_affiche_un_etat_vide_sans_planter(self):
        """
        Un directeur pas encore rattaché à un département ne doit jamais
        déclencher d'erreur serveur (AttributeError sur None), juste un
        rendu dégradé de son tableau de bord.
        """
        directeur = creer_directeur()  # pas de département associé
        client = Client()
        client.force_login(directeur.user)
        reponse = client.get(reverse('appStage:dashboard_directeur'))
        self.assertEqual(reponse.status_code, 200)
