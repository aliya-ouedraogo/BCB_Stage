from django.core import mail
from django.test import Client
from django.urls import reverse

from appStage.models import DemandeEncadrement, Notification, Stage
from appStage.tests.helpers import (
    SynchronousTestCase,
    creer_departement,
    creer_directeur,
    creer_stage,
    creer_stagiaire_direct,
    creer_tuteur,
)


class DemandeEncadrementModelTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.departement = creer_departement()
        self.directeur = creer_directeur(departement=self.departement)
        self.tuteur = creer_tuteur()
        self.stagiaire = creer_stagiaire_direct()
        self.stage = creer_stage(self.stagiaire, departement=self.departement)
        self.demande = DemandeEncadrement.objects.create(
            stage=self.stage, maitre_de_stage_demande=self.tuteur, proposee_par=self.directeur,
        )

    def test_notifier_tuteur_envoie_un_email_et_une_notification(self):
        self.demande.notifier_tuteur()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.tuteur.user.email])
        self.assertTrue(Notification.objects.filter(destinataire=self.tuteur.user).exists())

    def test_accepter_affecte_le_maitre_de_stage_et_previent_stagiaire_et_directeur(self):
        self.demande.accepter()

        self.stage.refresh_from_db()
        self.assertEqual(self.stage.maitre_de_stage, self.tuteur)

        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.ACCEPTEE)
        self.assertIsNotNone(self.demande.date_reponse)

        destinataires = {e.to[0] for e in mail.outbox}
        self.assertIn(self.stagiaire.user.email, destinataires)
        self.assertIn(self.directeur.user.email, destinataires)
        self.assertEqual(len(mail.outbox), 2)

    def test_refuser_avec_motif_ne_previent_que_le_directeur(self):
        motif = "Charge de travail trop importante actuellement."
        self.demande.refuser(motif)

        self.stage.refresh_from_db()
        self.assertIsNone(self.stage.maitre_de_stage)

        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.REFUSEE)
        self.assertEqual(self.demande.motif_refus, motif)

        # Un seul email envoyé, uniquement au directeur.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.directeur.user.email])
        self.assertIn(motif, mail.outbox[0].body)

        # Le stagiaire ne doit recevoir ni email ni notification suite à un refus.
        self.assertFalse(Notification.objects.filter(destinataire=self.stagiaire.user).exists())


class RepondreDemandeEncadrementVueTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.departement = creer_departement()
        self.directeur = creer_directeur(departement=self.departement)
        self.tuteur = creer_tuteur()
        self.stagiaire = creer_stagiaire_direct()
        self.stage = creer_stage(self.stagiaire, departement=self.departement)
        self.demande = DemandeEncadrement.objects.create(
            stage=self.stage, maitre_de_stage_demande=self.tuteur, proposee_par=self.directeur,
        )
        self.client = Client()
        self.client.force_login(self.tuteur.user)

    def test_accepter_via_la_vue(self):
        url = reverse('appStage:repondre_demande_encadrement', args=[self.demande.id, 'accepter'])
        reponse = self.client.post(url)
        self.assertEqual(reponse.status_code, 302)

        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.ACCEPTEE)

    def test_refuser_sans_motif_est_rejete(self):
        url = reverse('appStage:repondre_demande_encadrement', args=[self.demande.id, 'refuser'])
        reponse = self.client.post(url, {'motif': ''})
        self.assertEqual(reponse.status_code, 302)

        self.demande.refresh_from_db()
        # Toujours en attente : le motif vide n'a pas dû être accepté.
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.EN_ATTENTE)
        self.assertEqual(len(mail.outbox), 0)

    def test_refuser_avec_motif_fonctionne(self):
        url = reverse('appStage:repondre_demande_encadrement', args=[self.demande.id, 'refuser'])
        reponse = self.client.post(url, {'motif': 'Indisponible ce trimestre.'})
        self.assertEqual(reponse.status_code, 302)

        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.REFUSEE)
        self.assertEqual(self.demande.motif_refus, 'Indisponible ce trimestre.')

    def test_un_autre_maitre_de_stage_ne_peut_pas_repondre_a_la_place(self):
        autre_tuteur = creer_tuteur(username='tuteur2')
        client = Client()
        client.force_login(autre_tuteur.user)
        url = reverse('appStage:repondre_demande_encadrement', args=[self.demande.id, 'accepter'])
        reponse = client.post(url)
        # get_object_or_404 filtre sur maitre_de_stage_demande=request.user.profil_maitre_stage.
        self.assertEqual(reponse.status_code, 404)

        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeEncadrement.Statut.EN_ATTENTE)
