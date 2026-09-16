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
    ProfilDirecteur,
    ProfilMaitreStage,
    ProfilRH,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


class Command(BaseCommand):
    help = "Génère un jeu de données de démonstration pour tester les 4 tableaux de bord (RH, Directeur, Maître de stage, Stagiaire)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(self.style.ERROR(
                "Commande bloquée : DEBUG=False (probable environnement de production). "
                "Cette commande supprime tous les comptes existants, à ne lancer qu'en local/démo."
            ))
            return

        self.stdout.write("Nettoyage des données existantes...")
        for model in [Presence, RapportHebdomadaire, Mission, Evaluation, Entretien,
                      DemandeEncadrement, DocumentStage, Stage, Candidature,
                      ProfilStagiaire, ProfilRH, ProfilMaitreStage, ProfilDirecteur, Departement]:
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

        # --- Directeurs de service ---
        # (2 directeurs : un avec un service actif à gérer, propositions en
        # attente, stagiaires sans maître de stage, l'autre juste pour montrer
        # un service "calme", tout est déjà assigné.)
        def creer_directeur(username, prenom, nom, poste, departement):
            u = User.objects.create_user(
                username=username, email=f"{username}@bcbstageflow.test", password='DemoPass123',
                first_name=prenom, last_name=nom, role=User.Role.DIRECTEUR,
            )
            profil = u.profil_directeur  # créé automatiquement par le signal post_save
            profil.poste = poste
            profil.save()
            departement.directeur = profil
            departement.save(update_fields=['directeur'])
            return profil

        directeur_dev = creer_directeur('b.compaore', 'Boukari', 'Compaoré', "Directeur Technique", dep_dev)
        directeur_marketing = creer_directeur('r.sana', 'Rasmata', 'Sana', "Directrice Marketing", dep_marketing)
        # dep_rh et dep_reseau restent volontairement SANS directeur, pour
        # tester le cas "service sans directeur" (le RH peut quand même y
        # affecter un stagiaire, mais personne ne recevra la notification
        # d'affectation tant qu'un directeur n'y est pas assigné).

        # --- Maîtres de stage ---
        # (2 maîtres de stage pour pouvoir tester l'acceptation/le refus
        # d'une proposition d'encadrement, et l'assignation de missions à
        # plusieurs stagiaires différents.)
        maitre_kader_user = User.objects.create_user(
            username='M.Kader', email='kader@bcbstageflow.test', password='DemoPass123',
            first_name='', last_name='M. Kader', role=User.Role.MAITRE_STAGE,
        )
        profil_kader = maitre_kader_user.profil_maitre_stage  # créé automatiquement par le signal post_save
        profil_kader.poste = "Lead Developer"
        profil_kader.departement_affiliation = "Développement Web"
        profil_kader.save()

        maitre_konate_user = User.objects.create_user(
            username='F.Konate', email='konate@bcbstageflow.test', password='DemoPass123',
            first_name='', last_name='F. Konaté', role=User.Role.MAITRE_STAGE,
        )
        profil_konate = maitre_konate_user.profil_maitre_stage
        profil_konate.poste = "Cheffe de Projet Marketing"
        profil_konate.departement_affiliation = "Marketing Digital"
        profil_konate.save()

        # --- Stagiaires ---
        def creer_stagiaire(username, prenom, nom, filiere, annee):
            u = User.objects.create_user(
                username=username, email=f"{username}@bcbstageflow.test", password='DemoPass123',
                first_name=prenom, last_name=nom, role=User.Role.STAGIAIRE,
            )
            return ProfilStagiaire.objects.create(user=u, filiere=filiere, annee_etude=annee)

        profil_mariam = creer_stagiaire('mariam', 'Mariam', 'Oued', 'Développement Web', 'LICENCE_3')
        profil_succes = creer_stagiaire('succes', 'Succes', 'Da', 'Marketing Digital', 'MASTER_1')
        profil_aliya = creer_stagiaire('aliya', 'Aliya', 'Oued', 'Ressources Humaines', 'LICENCE_2')
        profil_geoffroy = creer_stagiaire('geoffroy', 'Geoffroy', 'Yam', 'Marketing Digital', 'MASTER_2')
        profil_awa = creer_stagiaire('awa', 'Awa', 'Zongo', 'Réseaux et Télécoms', 'LICENCE_3')

        aujourdhui = timezone.now().date()

        # --- Stage Mariam : en cours, maître de stage déjà assigné et actif ---
        stage_mariam = Stage.objects.create(
            stagiaire=profil_mariam, departement=dep_dev, maitre_de_stage=profil_kader,
            intitule_poste="Stagiaire Ingénieur Logiciel",
            date_debut=aujourdhui - datetime.timedelta(weeks=4),
            date_fin=aujourdhui + datetime.timedelta(weeks=8),
            statut=Stage.Statut.EN_COURS, avec_soutenance=True,
        )
        Mission.objects.create(
            stage=stage_mariam, titre="Intégration API, Phase 2", equipe="Équipe Backend",
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
        # Rapport déposé par la stagiaire, notifie automatiquement son
        # maître de stage ET le directeur du service (nouveau comportement :
        # la stagiaire ne choisit plus de destinataire, elle dépose simplement).
        DocumentStage.objects.create(
            stage=stage_mariam, nom="Rapport_Hebdo_S3.docx", type_document=DocumentStage.TypeDocument.RAPPORT,
            destinataire=DocumentStage.Destinataire.TUTEUR, ajoute_par=profil_mariam.user,
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

        # --- Stage Succes : en cours, maître de stage assigné, progression avancée ---
        stage_succes = Stage.objects.create(
            stagiaire=profil_succes, departement=dep_marketing, maitre_de_stage=profil_konate,
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
        # Contrat envoyé par le RH, en attente de signature, pour tester la
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

        # --- Stage Aliya : en cours, PAS de maître de stage, proposition du
        # directeur en attente de réponse (teste dashboard_tuteur ET
        # affecter_maitre_stage/dashboard_directeur en même temps). Le
        # service RH n'a pas de directeur : cette proposition est donc créée
        # ici directement (par le RH lui-même en amont dans la vraie vie,
        # via /admin/, faute de directeur pour le faire) plutôt que déposée
        # par un compte directeur inexistant.
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
        # Convention envoyée par le RH à la stagiaire, pas encore signée,
        # alimente le panneau "À faire" du RH ET le compteur de signatures.
        DocumentStage.objects.create(
            stage=stage_aliya, nom="Convention_Aliya_Oued.pdf",
            type_document=DocumentStage.TypeDocument.CONVENTION,
            destinataire=DocumentStage.Destinataire.STAGIAIRE, ajoute_par=rh_user,
            statut_signature=DocumentStage.StatutSignature.EN_ATTENTE,
        )
        demande_aliya = DemandeEncadrement.objects.create(
            stage=stage_aliya, maitre_de_stage_demande=profil_kader,
        )

        # --- Stage Awa : en cours, service SANS directeur et SANS maître de
        # stage, pour tester l'affichage "service sans directeur" côté RH
        # (personne à notifier automatiquement) et le cas non bloquant.
        stage_awa = Stage.objects.create(
            stagiaire=profil_awa, departement=dep_reseau,
            intitule_poste="Stagiaire Réseaux",
            date_debut=aujourdhui - datetime.timedelta(weeks=1),
            date_fin=aujourdhui + datetime.timedelta(weeks=11),
            statut=Stage.Statut.EN_COURS, avec_soutenance=False,
        )

        # --- Stage Geoffroy : terminé, avec historique complet (évaluation finale incluse) ---
        stage_geoffroy = Stage.objects.create(
            stagiaire=profil_geoffroy, departement=dep_marketing, maitre_de_stage=profil_konate,
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
            description="Livrable resté ouvert après la fin du stage, objectif non finalisé à temps.",
            echeance=aujourdhui - datetime.timedelta(weeks=3), statut=Mission.Statut.EN_COURS,
        )
        Evaluation.objects.create(
            stage=stage_geoffroy, type_evaluation=Evaluation.TypeEvaluation.FINALE,
            note_technique=13, note_autonomie=12, note_communication=15, note_ponctualite=11,
            commentaire="Bon sens créatif et bonne intégration à l'équipe, mais plusieurs échéances n'ont pas "
                        "été tenues sur la fin du stage. À accompagner davantage sur la gestion du temps.",
        )

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
            nom_complet="Karim Sawadogo", email="karim.sawadogo@example.com", telephone="+22670000002",
            poste_souhaite="Stagiaire Développeur Mobile", filiere="Développement Web", annee_etude='LICENCE_3',
            departement_souhaite=dep_dev, avec_soutenance_souhaite=False,
        )
        Candidature.objects.create(
            nom_complet="Issa Kaboré", email="issa.kabore@example.com", telephone="+22670000003",
            poste_souhaite="Stagiaire Comptabilité", filiere="Finance et Comptabilité", annee_etude='MASTER_1',
        )
        c_refusee = Candidature.objects.get(nom_complet="Issa Kaboré")
        c_refusee.refuser("Profil ne correspondant pas aux prérequis techniques du poste.", profil_rh)

        # Candidature acceptée à l'instant du seed, dans un service AVEC
        # directeur (dep_rh n'en a pas, on utilise dep_dev ici), pour
        # vérifier tout de suite dans la console/boîte mail que la
        # notification au directeur part bien à l'acceptation.
        c_acceptee = Candidature.objects.create(
            nom_complet="Fatou Traoré", email="fatou.traore@example.com", telephone="+22670000004",
            poste_souhaite="Stagiaire Assistante RH", filiere="Ressources Humaines", annee_etude='LICENCE_2',
            departement_souhaite=dep_dev, avec_soutenance_souhaite=True,
        )
        c_acceptee.programmer_entretien(
            traite_par=profil_rh,
            date_entretien=aujourdhui + datetime.timedelta(days=3),
            avec_soutenance=True,
        )
        _, stage_fatou, _ = c_acceptee.finaliser_stage(
            date_debut=aujourdhui + datetime.timedelta(weeks=1),
            date_fin=aujourdhui + datetime.timedelta(weeks=13),
        )
        # finaliser_stage() ne fait plus l'affectation de service (déplacée
        # sur la page Affectation dédiée) : on la simule ici pour retrouver
        # le comportement de démo attendu (notification envoyée à b.compaore).
        stage_fatou.departement = dep_dev
        stage_fatou.save(update_fields=['departement'])
        stage_fatou.notifier_directeur_affectation()

        self.stdout.write(self.style.SUCCESS(
            "\nDonnées de démo créées. Comptes de connexion (mot de passe : DemoPass123) :\n"
            "  - RH               : adminhr\n"
            "  - Directeur        : b.compaore (Développement Web), service actif, tout assigné\n"
            "  - Directeur        : r.sana (Marketing Digital), service actif, tout assigné\n"
            "  - Maître de stage  : M.Kader (Développement Web), encadre Mariam, proposition en\n"
            "                       attente de sa réponse pour Aliya (dashboard_tuteur)\n"
            "  - Maître de stage  : F.Konate (Marketing Digital), encadre Succes et Geoffroy (terminé)\n"
            "  - Stagiaire        : mariam (dashboard complet, en cours, maître de stage assigné)\n"
            "  - Stagiaire        : succes (en cours, avancé, maître de stage assigné)\n"
            "  - Stagiaire        : aliya (en cours, SANS maître de stage, proposition en attente\n"
            "                       de réponse de M.Kader ; le service RH n'a pas de directeur)\n"
            "  - Stagiaire        : awa (en cours, service Réseaux SANS directeur ni maître de stage,\n"
            "                       cas 'personne à notifier automatiquement')\n"
            "  - Stagiaire        : geoffroy (stage terminé, évaluation finale, entretien de sortie)\n"
            "  - Fatou Traoré     : candidature acceptée à l'instant dans le service Développement Web\n"
            "                       (avec directeur), vérifiez la notification envoyée à b.compaore\n"
            "                       (console e-mail si aucun serveur SMTP configuré) ; pas de compte\n"
            "                       utilisable avant activation par e-mail.\n"
        ))
