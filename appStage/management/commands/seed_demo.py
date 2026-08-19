import datetime
import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from appStage.models import (
    Candidature,
    Departement,
    DemandeEncadrement,
    DocumentStage,
    Entretien,
    Evaluation,
    Mission,
    Presence,
    ProfilMaitreStage,
    ProfilRH,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


class Command(BaseCommand):
    help = "Génère un jeu de données de démonstration pour tester les 3 tableaux de bord."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(self.style.ERROR(
                "Commande bloquée : DEBUG=False (probable environnement de production). "
                "Cette commande supprime tous les comptes existants — à ne lancer qu'en local/démo."
            ))
            return

        self.stdout.write("Nettoyage des données existantes...")
        for model in [Presence, RapportHebdomadaire, Mission, Evaluation, Entretien,
                      DemandeEncadrement, DocumentStage, Stage, Candidature,
                      ProfilStagiaire, ProfilRH, ProfilMaitreStage, Departement]:
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

        # --- Départements ---
        dep_dev = Departement.objects.create(nom="Développement Web", agence="Ouagadougou")
        dep_rh = Departement.objects.create(nom="Ressources Humaines", agence="Ouagadougou")
        dep_marketing = Departement.objects.create(nom="Marketing Digital", agence="Bobo-Dioulasso")

        # --- RH ---
        rh_user = User.objects.create_user(
            username='adminhr', email='rh@bcbstageflow.test', password='DemoPass123',
            first_name='Admin', last_name='HR', role=User.Role.RH,
        )
        profil_rh = ProfilRH.objects.create(user=rh_user, service="Recrutement")

        # --- Maître de stage ---
        tuteur_user = User.objects.create_user(
            username='dr.lemaire', email='lemaire@bcbstageflow.test', password='DemoPass123',
            first_name='', last_name='Dr. Lemaire', role=User.Role.MAITRE_STAGE,
        )
        profil_tuteur = ProfilMaitreStage.objects.create(
            user=tuteur_user, poste="Lead Developer", departement_affiliation="Développement Web"
        )

        # --- Stagiaires ---
        def creer_stagiaire(username, prenom, nom, filiere, annee):
            u = User.objects.create_user(
                username=username, email=f"{username}@bcbstageflow.test", password='DemoPass123',
                first_name=prenom, last_name=nom, role=User.Role.STAGIAIRE,
            )
            return ProfilStagiaire.objects.create(user=u, filiere=filiere, annee_etude=annee)

        profil_thomas = creer_stagiaire('thomasd', 'Thomas', 'Dubois', 'Développement Web', '3ème Année')
        profil_sophie = creer_stagiaire('sophiem', 'Sophie', 'Martin', 'Marketing Digital', '2ème Année')
        profil_lucas = creer_stagiaire('lucasb', 'Lucas', 'Bernard', 'Ressources Humaines', '1ère Année')
        profil_emma = creer_stagiaire('emmap', 'Emma', 'Petit', 'Design Graphique', 'Terminée')

        aujourdhui = timezone.now().date()

        # --- Stage principal (Thomas) : en cours, avec tuteur, semaine 4/12 ---
        stage_thomas = Stage.objects.create(
            stagiaire=profil_thomas, departement=dep_dev, maitre_de_stage=profil_tuteur,
            intitule_poste="Stagiaire Ingénieur Logiciel",
            date_debut=aujourdhui - datetime.timedelta(weeks=4),
            date_fin=aujourdhui + datetime.timedelta(weeks=8),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        Mission.objects.create(
            stage=stage_thomas, titre="Intégration API — Phase 2", equipe="Équipe Backend",
            description="Finaliser la migration des anciens points de terminaison vers GraphQL.",
            echeance=aujourdhui + datetime.timedelta(days=3), statut=Mission.Statut.EN_COURS,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_thomas, numero_semaine=1, statut=RapportHebdomadaire.Statut.VALIDE,
        )
        DocumentStage.objects.create(
            stage=stage_thomas, nom="Convention_Stage_Signee.pdf", type_document=DocumentStage.TypeDocument.CONVENTION,
            statut_signature=DocumentStage.StatutSignature.SIGNE, date_signature=aujourdhui - datetime.timedelta(weeks=4),
        )
        DocumentStage.objects.create(
            stage=stage_thomas, nom="Rapport_Hebdo_S3.docx", type_document=DocumentStage.TypeDocument.RAPPORT,
        )
        Evaluation.objects.create(
            stage=stage_thomas, type_evaluation=Evaluation.TypeEvaluation.MI_PARCOURS,
            note=17.5,
            commentaire="Thomas a fait preuve d'une excellente initiative sur les dernières tâches liées à l'API. "
                        "La qualité du code est constamment élevée. Point d'attention : améliorer la documentation.",
        )
        for i in range(20):
            jour = aujourdhui - datetime.timedelta(days=i)
            Presence.objects.create(
                stage=stage_thomas, date=jour,
                present=(i != 5), justifie=(i == 5), valide_par_tuteur=(i > 1),
            )

        # --- Stage Sophie : en cours, tuteur assigné, progression 75% ---
        stage_sophie = Stage.objects.create(
            stagiaire=profil_sophie, departement=dep_marketing, maitre_de_stage=profil_tuteur,
            intitule_poste="Stagiaire Marketing Digital",
            date_debut=aujourdhui - datetime.timedelta(weeks=9),
            date_fin=aujourdhui + datetime.timedelta(weeks=3),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_sophie, numero_semaine=9, statut=RapportHebdomadaire.Statut.EN_ATTENTE,
            date_soumission=timezone.now() - datetime.timedelta(hours=2),
        )

        # --- Stage Lucas : en cours, tuteur assigné, en révision ---
        stage_lucas = Stage.objects.create(
            stagiaire=profil_lucas, departement=dep_rh, maitre_de_stage=profil_tuteur,
            intitule_poste="Stagiaire Ressources Humaines",
            date_debut=aujourdhui - datetime.timedelta(weeks=5),
            date_fin=aujourdhui + datetime.timedelta(weeks=7),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_lucas, numero_semaine=5, statut=RapportHebdomadaire.Statut.EN_ATTENTE,
            date_soumission=timezone.now() - datetime.timedelta(days=1),
        )

        # --- Stage Emma : terminé, objectifs en retard, sans tuteur assigné ---
        stage_emma = Stage.objects.create(
            stagiaire=profil_emma, departement=dep_marketing,
            intitule_poste="Stagiaire Design Graphique",
            date_debut=aujourdhui - datetime.timedelta(weeks=26),
            date_fin=aujourdhui - datetime.timedelta(weeks=2),
            statut=Stage.Statut.TERMINE, avec_soutenance=False,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_emma, numero_semaine=1, statut=RapportHebdomadaire.Statut.EN_RETARD,
            date_soumission=timezone.now() - datetime.timedelta(days=2),
        )

        # --- Convention non signée (Lucas), pour le panneau "À faire" du RH ---
        DocumentStage.objects.create(
            stage=stage_lucas, nom="Convention_Lucas_Bernard.pdf",
            type_document=DocumentStage.TypeDocument.CONVENTION,
            statut_signature=DocumentStage.StatutSignature.EN_ATTENTE,
        )

        # --- Demande d'encadrement en attente (Emma vers Dr. Lemaire) ---
        DemandeEncadrement.objects.create(stage=stage_emma, maitre_de_stage_demande=profil_tuteur)

        # --- Entretien RH consigné ---
        Entretien.objects.create(
            stage=stage_thomas, rh=profil_rh,
            date=timezone.now() - datetime.timedelta(days=10),
            compte_rendu="Point d'intégration à un mois : bonne adaptation à l'équipe, aucun blocage signalé.",
        )

        # --- Candidatures en attente / refusée (pour le dashboard RH) ---
        Candidature.objects.create(
            nom_complet="Awa Zongo", email="awa.zongo@example.com", telephone="+226 70 00 00 01",
            poste_souhaite="Stagiaire Data Analyst",
        )
        Candidature.objects.create(
            nom_complet="Karim Sawadogo", email="karim.sawadogo@example.com", telephone="+226 70 00 00 02",
            poste_souhaite="Stagiaire Développeur Mobile",
        )
        c_refusee = Candidature.objects.create(
            nom_complet="Issa Kaboré", email="issa.kabore@example.com", telephone="+226 70 00 00 03",
            poste_souhaite="Stagiaire Comptabilité",
        )
        c_refusee.refuser("Profil ne correspondant pas aux prérequis techniques du poste.", profil_rh)

        self.stdout.write(self.style.SUCCESS(
            "\nDonnées de démo créées. Comptes de connexion (mot de passe : DemoPass123) :\n"
            "  - RH        : adminhr\n"
            "  - Tuteur    : dr.lemaire\n"
            "  - Stagiaire : thomasd (dashboard complet, en cours)\n"
            "  - Stagiaire : sophiem / lucasb / emmap (variantes de statut)\n"
        ))
