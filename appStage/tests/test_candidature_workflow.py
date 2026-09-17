import datetime

from django.core import mail
from django.utils import timezone

from appStage.models import Candidature, Stage
from appStage.tests.helpers import SynchronousTestCase, creer_candidature, creer_rh


class ProgrammerEntretienTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.rh = creer_rh()
        self.candidature = creer_candidature()

    def test_programme_un_entretien_et_change_le_statut(self):
        date_entretien = timezone.now().date() + datetime.timedelta(days=5)
        self.candidature.programmer_entretien(
            traite_par=self.rh, date_entretien=date_entretien, avec_soutenance=True,
        )
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.ENTRETIEN)
        self.assertEqual(self.candidature.date_entretien, date_entretien)
        self.assertEqual(self.candidature.traite_par, self.rh)

    def test_envoie_un_email_au_candidat(self):
        date_entretien = timezone.now().date() + datetime.timedelta(days=5)
        self.candidature.programmer_entretien(
            traite_par=self.rh, date_entretien=date_entretien,
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.candidature.email])
        self.assertIn(date_entretien.strftime('%d/%m/%Y'), email.body)


class FinaliserStageTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.rh = creer_rh()
        self.candidature = creer_candidature()
        self.candidature.programmer_entretien(
            traite_par=self.rh, date_entretien=timezone.now().date(),
        )
        mail.outbox.clear()

    def test_cree_le_compte_le_profil_et_le_stage_sans_departement(self):
        date_debut = timezone.now().date() + datetime.timedelta(days=10)
        date_fin = date_debut + datetime.timedelta(days=90)
        user, stage, lien = self.candidature.finaliser_stage(date_debut=date_debut, date_fin=date_fin)

        self.assertEqual(user.email, self.candidature.email)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(stage.date_debut, date_debut)
        self.assertEqual(stage.date_fin, date_fin)
        self.assertIsNone(stage.departement)
        self.assertEqual(stage.statut, Stage.Statut.A_VENIR)

        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.ACCEPTEE)
        self.assertEqual(self.candidature.stagiaire_cree, stage.stagiaire)
        self.assertTrue(lien)

    def test_email_de_confirmation_mentionne_la_date_de_debut(self):
        date_debut = timezone.now().date() + datetime.timedelta(days=10)
        date_fin = date_debut + datetime.timedelta(days=90)
        self.candidature.finaliser_stage(date_debut=date_debut, date_fin=date_fin)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.candidature.email])
        self.assertIn(date_debut.strftime('%d/%m/%Y'), email.body)


class RefuserCandidatureTests(SynchronousTestCase):
    def setUp(self):
        super().setUp()
        self.rh = creer_rh()
        self.candidature = creer_candidature()

    def test_refus_sans_motif_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            self.candidature.refuser('', self.rh)

    def test_refus_avec_motif_envoie_un_email_poli_avec_le_motif(self):
        motif = "Profil ne correspondant pas aux prérequis techniques du poste."
        self.candidature.refuser(motif, self.rh)

        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.REFUSEE)
        self.assertEqual(self.candidature.motif_refus, motif)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.candidature.email])
        self.assertIn(motif, email.body)
        # Poli : remerciements + souhait de succès, pas juste un refus sec.
        self.assertIn("remercions", email.body.lower())
