import datetime

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
        dep_reseau = Departement.objects.create(nom="Réseaux et Télécoms", agence="Ouagadougou")

        # --- RH ---
        rh_user = User.objects.create_user(
            username='adminhr', email='rh@bcbstageflow.test', password='DemoPass123',
            first_name='Admin', last_name='HR', role=User.Role.RH,
        )
        profil_rh = rh_user.profil_rh  # créé automatiquement par le signal post_save
        profil_rh.service = "Recrutement"
        profil_rh.save()

        # --- Maîtres de stage ---
        # (2 tuteurs pour pouvoir tester le choix du tuteur côté stagiaire et
        # l'assignation de missions à plusieurs stagiaires différents côté tuteur.)
        tuteur_user = User.objects.create_user(
            username='M.Kader', email='kader@bcbstageflow.test', password='DemoPass123',
            first_name='', last_name='M. Kader', role=User.Role.MAITRE_STAGE,
        )
        profil_tuteur = tuteur_user.profil_maitre_stage  # créé automatiquement par le signal post_save
        profil_tuteur.poste = "Lead Developer"
        profil_tuteur.departement_affiliation = "Développement Web"
        profil_tuteur.save()

        tuteur2_user = User.objects.create_user(
            username='F.Konate', email='konate@bcbstageflow.test', password='DemoPass123',
            first_name='', last_name='F. Konaté', role=User.Role.MAITRE_STAGE,
        )
        profil_tuteur2 = tuteur2_user.profil_maitre_stage
        profil_tuteur2.poste = "Cheffe de Projet Marketing"
        profil_tuteur2.departement_affiliation = "Marketing Digital"
        profil_tuteur2.save()

        # --- Stagiaires ---
        def creer_stagiaire(username, prenom, nom, filiere, annee):
            u = User.objects.create_user(
                username=username, email=f"{username}@bcbstageflow.test", password='DemoPass123',
                first_name=prenom, last_name=nom, role=User.Role.STAGIAIRE,
            )
            return ProfilStagiaire.objects.create(user=u, filiere=filiere, annee_etude=annee)

        profil_mariam = creer_stagiaire('mariam', 'Mariam', 'Oued', 'Développement Web', '1ère Année')
        profil_succes = creer_stagiaire('succes', 'Succes', 'Da', 'Reseau et Telecom', '3ème Année')
        profil_aliya = creer_stagiaire('aliya', 'Aliya', 'Oued', 'Développement Web', '2ème Année')
        profil_geoffroy = creer_stagiaire('geoffroy', 'Geoffroy', 'Yam', 'Reseau et Telecom', 'Terminée')

        aujourdhui = timezone.now().date()

        # --- Stage principal (Mariam) : en cours, avec tuteur, semaine 4/12 ---
        stage_mariam = Stage.objects.create(
            stagiaire=profil_mariam, departement=dep_dev, maitre_de_stage=profil_tuteur,
            intitule_poste="Stagiaire Ingénieur Logiciel",
            date_debut=aujourdhui - datetime.timedelta(weeks=4),
            date_fin=aujourdhui + datetime.timedelta(weeks=8),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        Mission.objects.create(
            stage=stage_mariam, titre="Intégration API — Phase 2", equipe="Équipe Backend",
            description="Finaliser la migration des anciens points de terminaison vers GraphQL.",
            echeance=aujourdhui + datetime.timedelta(days=3), statut=Mission.Statut.EN_COURS,
        )
        Mission.objects.create(
            stage=stage_mariam, titre="Correction de bugs", equipe="Maintenance Sprint 4",
            description="Résoudre les tickets de bugs remontés en fin de sprint précédent.",
            echeance=aujourdhui - datetime.timedelta(days=4), statut=Mission.Statut.TERMINEE,
        )
        Mission.objects.create(
            stage=stage_mariam, titre="Tests unitaires", equipe="Assurance Qualité",
            description="Écrire la suite de tests unitaires pour le module d'authentification.",
            echeance=aujourdhui + datetime.timedelta(days=10), statut=Mission.Statut.A_FAIRE,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_mariam, numero_semaine=1, statut=RapportHebdomadaire.Statut.VALIDE,
        )
        # Convention envoyée par le RH, déjà signée par la stagiaire.
        DocumentStage.objects.create(
            stage=stage_mariam, nom="Convention_Stage_Signee.pdf", type_document=DocumentStage.TypeDocument.CONVENTION,
            destinataire=DocumentStage.Destinataire.STAGIAIRE, ajoute_par=rh_user,
            statut_signature=DocumentStage.StatutSignature.SIGNE, date_signature=aujourdhui - datetime.timedelta(weeks=4),
        )
        # Rapport envoyé par la stagiaire à son tuteur.
        DocumentStage.objects.create(
            stage=stage_mariam, nom="Rapport_Hebdo_S3.docx", type_document=DocumentStage.TypeDocument.RAPPORT,
            destinataire=DocumentStage.Destinataire.TUTEUR, ajoute_par=profil_mariam.user,
        )
        # Pièce administrative envoyée directement au RH (pas au tuteur).
        DocumentStage.objects.create(
            stage=stage_mariam, nom="Piece_Identite_Mariam.pdf", type_document=DocumentStage.TypeDocument.AUTRE,
            destinataire=DocumentStage.Destinataire.RH, ajoute_par=profil_mariam.user,
        )
        Evaluation.objects.create(
            stage=stage_mariam, type_evaluation=Evaluation.TypeEvaluation.MI_PARCOURS,
            note_technique=17, note_autonomie=15, note_communication=16, note_ponctualite=18,
            commentaire="Mariam a fait preuve d'une excellente initiative sur les dernières tâches liées à l'API. "
                        "La qualité du code est constamment élevée. Point d'attention : améliorer la documentation.",
        )
        for i in range(20):
            jour = aujourdhui - datetime.timedelta(days=i)
            Presence.objects.create(
                stage=stage_mariam, date=jour,
                present=(i != 5), justifie=(i == 5), valide_par_tuteur=(i > 1),
            )

        # --- Stage Succes : en cours, tuteur assigné, progression avancée ---
        stage_succes = Stage.objects.create(
            stagiaire=profil_succes, departement=dep_marketing, maitre_de_stage=profil_tuteur,
            intitule_poste="Stagiaire Marketing Digital",
            date_debut=aujourdhui - datetime.timedelta(weeks=9),
            date_fin=aujourdhui + datetime.timedelta(weeks=3),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        Mission.objects.create(
            stage=stage_succes, titre="Campagne réseaux sociaux Q3", equipe="Équipe Marketing",
            description="Planifier et publier le calendrier de contenu du trimestre.",
            echeance=aujourdhui + datetime.timedelta(days=6), statut=Mission.Statut.EN_COURS,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_succes, numero_semaine=9, statut=RapportHebdomadaire.Statut.EN_ATTENTE,
            date_soumission=timezone.now() - datetime.timedelta(hours=2),
        )
        # Contrat envoyé par le RH, en attente de signature — pour tester la
        # page Documents du RH (section "Envoyés") et le compteur associé.
        DocumentStage.objects.create(
            stage=stage_succes, nom="Contrat_Stage_Succes.pdf", type_document=DocumentStage.TypeDocument.CONTRAT,
            destinataire=DocumentStage.Destinataire.STAGIAIRE, ajoute_par=rh_user,
            statut_signature=DocumentStage.StatutSignature.EN_ATTENTE,
        )
        for i in range(10):
            jour = aujourdhui - datetime.timedelta(days=i)
            Presence.objects.create(
                stage=stage_succes, date=jour, present=True, valide_par_tuteur=(i > 0),
            )

        # --- Stage Aliya : en cours, PAS de tuteur assigné (demande en attente) ---
        stage_aliya = Stage.objects.create(
            stagiaire=profil_aliya, departement=dep_rh,
            intitule_poste="Stagiaire Ressources Humaines",
            date_debut=aujourdhui - datetime.timedelta(weeks=5),
            date_fin=aujourdhui + datetime.timedelta(weeks=7),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_aliya, numero_semaine=5, statut=RapportHebdomadaire.Statut.EN_ATTENTE,
            date_soumission=timezone.now() - datetime.timedelta(days=1),
        )
        # Convention envoyée par le RH à la stagiaire, pas encore signée —
        # alimente le panneau "À faire" du RH ET le compteur de signatures.
        DocumentStage.objects.create(
            stage=stage_aliya, nom="Convention_Aliya_Oued.pdf",
            type_document=DocumentStage.TypeDocument.CONVENTION,
            destinataire=DocumentStage.Destinataire.STAGIAIRE, ajoute_par=rh_user,
            statut_signature=DocumentStage.StatutSignature.EN_ATTENTE,
        )

        # --- Stage Geoffroy : terminé, avec historique complet (évaluation finale incluse) ---
        stage_geoffroy = Stage.objects.create(
            stagiaire=profil_geoffroy, departement=dep_marketing, maitre_de_stage=profil_tuteur2,
            intitule_poste="Stagiaire Design Graphique",
            date_debut=aujourdhui - datetime.timedelta(weeks=26),
            date_fin=aujourdhui - datetime.timedelta(weeks=2),
            statut=Stage.Statut.TERMINE, avec_soutenance=False,
        )
        RapportHebdomadaire.objects.create(
            stage=stage_geoffroy, numero_semaine=1, statut=RapportHebdomadaire.Statut.EN_RETARD,
            date_soumission=timezone.now() - datetime.timedelta(days=2),
        )
        Mission.objects.create(
            stage=stage_geoffroy, titre="Refonte de la charte graphique", equipe="Équipe Design",
            description="Livrable resté ouvert après la fin du stage — objectif non finalisé à temps.",
            echeance=aujourdhui - datetime.timedelta(weeks=3), statut=Mission.Statut.EN_COURS,
        )
        Evaluation.objects.create(
            stage=stage_geoffroy, type_evaluation=Evaluation.TypeEvaluation.FINALE,
            note_technique=13, note_autonomie=12, note_communication=15, note_ponctualite=11,
            commentaire="Bon sens créatif et bonne intégration à l'équipe, mais plusieurs échéances n'ont pas "
                        "été tenues sur la fin du stage. À accompagner davantage sur la gestion du temps.",
        )

        # --- Demande d'encadrement en attente (Aliya vers M. Kader) ---
        DemandeEncadrement.objects.create(stage=stage_aliya, maitre_de_stage_demande=profil_tuteur)

        # --- Entretiens RH consignés ---
        Entretien.objects.create(
            stage=stage_mariam, rh=profil_rh,
            date=timezone.now() - datetime.timedelta(days=10),
            compte_rendu="Point d'intégration à un mois : bonne adaptation à l'équipe, aucun blocage signalé.",
        )
        Entretien.objects.create(
            stage=stage_geoffroy, rh=profil_rh,
            date=timezone.now() - datetime.timedelta(weeks=3),
            compte_rendu="Entretien de fin de stage : bilan mitigé, retard sur plusieurs livrables évoqué avec le stagiaire.",
        )

        # --- Candidatures en attente / refusée / acceptée (pour le dashboard RH) ---
        Candidature.objects.create(
            nom_complet="Awa Zongo", email="awa.zongo@example.com", telephone="+226 70 00 00 01",
            poste_souhaite="Stagiaire Data Analyst",
            departement_souhaite=dep_reseau, avec_soutenance_souhaite=True,
        )
        Candidature.objects.create(
            nom_complet="Karim Sawadogo", email="karim.sawadogo@example.com", telephone="+226 70 00 00 02",
            poste_souhaite="Stagiaire Développeur Mobile",
            departement_souhaite=dep_dev, avec_soutenance_souhaite=False,
        )
        c_refusee = Candidature.objects.create(
            nom_complet="Issa Kaboré", email="issa.kabore@example.com", telephone="+226 70 00 00 03",
            poste_souhaite="Stagiaire Comptabilité",
        )
        c_refusee.refuser("Profil ne correspondant pas aux prérequis techniques du poste.", profil_rh)

        # Candidature déjà acceptée — pour tester le badge "Acceptée" et le compte
        # stagiaire fraîchement créé (mot de passe non défini, en attente d'activation
        # par e-mail — comportement normal du flux d'acceptation).
        c_acceptee = Candidature.objects.create(
            nom_complet="Fatou Traoré", email="fatou.traore@example.com", telephone="+226 70 00 00 04",
            poste_souhaite="Stagiaire Assistante RH", departement_souhaite=dep_rh, avec_soutenance_souhaite=True,
        )
        c_acceptee.accepter(
            departement=dep_rh, traite_par=profil_rh,
            date_debut=aujourdhui + datetime.timedelta(weeks=1),
            date_fin=aujourdhui + datetime.timedelta(weeks=13),
            avec_soutenance=True,
        )

        self.stdout.write(self.style.SUCCESS(
            "\nDonnées de démo créées. Comptes de connexion (mot de passe : DemoPass123) :\n"
            "  - RH          : adminhr\n"
            "  - Tuteur      : M.Kader (Dév Web / Marketing) — encadre Mariam et Succes\n"
            "  - Tuteur      : F.Konate (Marketing) — encadre Geoffroy (stage terminé)\n"
            "  - Stagiaire   : mariam (dashboard complet, en cours, tuteur assigné)\n"
            "  - Stagiaire   : succes (en cours, avancé, tuteur assigné)\n"
            "  - Stagiaire   : aliya (en cours, SANS tuteur — demande en attente à tester)\n"
            "  - Stagiaire   : geoffroy (stage terminé, évaluation finale, entretien de sortie)\n"
            "  - Fatou Traoré : candidature acceptée à l'instant — pas de compte utilisable "
            "avant activation par e-mail (lien affiché dans la console du serveur).\n"
        ))
