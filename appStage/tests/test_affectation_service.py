import datetime

from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from appStage.models import Notification, Stage
from appStage.tests.helpers import (
    SynchronousTestCase,
    creer_departement,
    creer_directeur,
    creer_rh,
    creer_stage,
    creer_stagiaire_direct,
)


class NotifierDirecteurAffectationTests(SynchronousTestCase):
    """Tests au niveau modèle : Stage.notifier_directeur_affectation()."""

    def setUp(self):
        super().setUp()
        self.departement = creer_departement()
        self.directeur = creer_directeur(departement=self.departement)
        self.stagiaire = creer_stagiaire_direct()

    def test_stagiaire_et_directeur_recoivent_chacun_un_email_et_une_notification(self):
        stage = creer_stage(self.stagiaire, departement=self.departement, statut=Stage.Statut.A_VENIR)
        stage.notifier_directeur_affectation()

        self.assertEqual(len(mail.outbox), 2)
        destinataires = {tuple(e.to) for e in mail.outbox}
        self.assertIn((self.stagiaire.user.email,), destinataires)
        self.assertIn((self.directeur.user.email,), destinataires)

        self.assertTrue(Notification.objects.filter(destinataire=self.stagiaire.user).exists())
        notif_directeur = Notification.objects.filter(destinataire=self.directeur.user).first()
        self.assertIsNotNone(notif_directeur)
        self.assertIn(reverse('appStage:affecter_maitre_stage'), notif_directeur.lien)

    def test_email_au_directeur_mentionne_la_date_de_debut_si_stage_a_venir(self):
        demain = timezone.now().date() + datetime.timedelta(days=3)
        stage = creer_stage(
            self.stagiaire, departement=self.departement,
            statut=Stage.Statut.A_VENIR, date_debut=demain,
        )
        stage.notifier_directeur_affectation()

        email_directeur = next(e for e in mail.outbox if e.to == [self.directeur.user.email])
        self.assertIn(demain.strftime('%d/%m/%Y'), email_directeur.body)

    def test_sans_directeur_rattache_seul_le_stagiaire_est_notifie(self):
        departement_orphelin = creer_departement(nom='Service sans directeur')
        stage = creer_stage(self.stagiaire, departement=departement_orphelin)
        stage.notifier_directeur_affectation()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.stagiaire.user.email])


class AffecterServiceVueTests(SynchronousTestCase):
    """Tests d'intégration sur la vue RH d'affectation à un service."""

    def setUp(self):
        super().setUp()
        self.rh = creer_rh()
        self.departement = creer_departement()
        self.directeur = creer_directeur(departement=self.departement)
        self.stagiaire = creer_stagiaire_direct()
        self.stage = creer_stage(self.stagiaire, departement=None)
        self.client = Client()
        self.client.force_login(self.rh.user)

    def test_premiere_affectation_renseigne_le_departement_et_notifie(self):
        reponse = self.client.post(reverse('appStage:affecter_service'), {
            'stage_id': self.stage.id,
            'departement': self.departement.id,
        })
        self.assertEqual(reponse.status_code, 302)

        self.stage.refresh_from_db()
        self.assertEqual(self.stage.departement, self.departement)
        self.assertEqual(len(mail.outbox), 2)

    def test_reaffectation_desassigne_le_maitre_de_stage_et_previent_le_nouveau_directeur(self):
        from appStage.tests.helpers import creer_tuteur

        tuteur = creer_tuteur()
        self.stage.departement = self.departement
        self.stage.maitre_de_stage = tuteur
        self.stage.save()

        nouveau_departement = creer_departement(nom='Comptabilité')
        nouveau_directeur = creer_directeur(username='directeur2', departement=nouveau_departement)

        reponse = self.client.post(reverse('appStage:affecter_service'), {
            'stage_id': self.stage.id,
            'departement': nouveau_departement.id,
        })
        self.assertEqual(reponse.status_code, 302)

        self.stage.refresh_from_db()
        self.assertEqual(self.stage.departement, nouveau_departement)
        self.assertIsNone(self.stage.maitre_de_stage)

        emails_destinataires = {e.to[0] for e in mail.outbox}
        self.assertIn(nouveau_directeur.user.email, emails_destinataires)

    def test_wrong_role_cannot_access(self):
        from appStage.tests.helpers import creer_tuteur

        tuteur = creer_tuteur()
        client = Client()
        client.force_login(tuteur.user)
        reponse = client.get(reverse('appStage:affecter_service'))
        self.assertEqual(reponse.status_code, 403)
