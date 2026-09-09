from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
import datetime

validateur_telephone_bf = RegexValidator(
    regex=r'^\+226[0-9]{8}$',
    message="Le numéro doit être au format +226 suivi de 8 chiffres.",
)


class AnneeEtude(models.TextChoices):
    LICENCE_1 = 'LICENCE_1', "1re année de Licence"
    LICENCE_2 = 'LICENCE_2', "2e année de Licence"
    LICENCE_3 = 'LICENCE_3', "3e année de Licence"
    MASTER_1 = 'MASTER_1', "1re année de Master"
    MASTER_2 = 'MASTER_2', "2e année de Master"


# =========================================================
# Utilisateur & rôles
# =========================================================

class User(AbstractUser):
    """
    Utilisateur custom. Le rôle détermine l'espace auquel la personne
    a accès (stagiaire / RH / maître de stage) et sert de base aux
    permissions et à la redirection après connexion.

    NB : les profils ci-dessous ne sont PAS des sous-classes de User
    (Django impose un seul modèle d'authentification pour toute
    l'app). Chaque profil lui est simplement associé en OneToOne.
    """

    class Role(models.TextChoices):
        STAGIAIRE = 'STAGIAIRE', 'Stagiaire'
        RH = 'RH', 'Ressources Humaines'
        MAITRE_STAGE = 'MAITRE_STAGE', 'Maître de Stage'
        DIRECTEUR = 'DIRECTEUR', 'Directeur de Service'

    role = models.CharField(max_length=20, choices=Role.choices)
    telephone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return self.get_full_name() or self.username

    def get_dashboard_url_name(self):
        """Nom de route (namespacé) du tableau de bord correspondant au rôle."""
        return {
            self.Role.STAGIAIRE: 'appStage:dashboard_stagiaire',
            self.Role.RH: 'appStage:dashboard_rh',
            self.Role.MAITRE_STAGE: 'appStage:dashboard_tuteur',
            self.Role.DIRECTEUR: 'appStage:dashboard_directeur',
        }.get(self.role, 'appStage:onboarding')


class ProfilStagiaire(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_stagiaire'
    )
    filiere = models.CharField(max_length=150, blank=True)
    annee_etude = models.CharField(max_length=20, choices=AnneeEtude.choices, blank=True)
    etablissement = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return str(self.user)

    @property
    def stage_actif(self):
        """
        Le stage à afficher sur le dashboard du stagiaire : en priorité un
        stage EN_COURS, sinon le plus proche A_VENIR (pour qu'un stagiaire
        fraîchement accepté voie déjà la structure de son dashboard,
        même avant le début officiel de son stage).
        """
        stage = self.stages.filter(statut=Stage.Statut.EN_COURS).first()
        if stage:
            return stage
        return self.stages.filter(statut=Stage.Statut.A_VENIR).order_by('date_debut').first()


class ProfilRH(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_rh'
    )
    service = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return str(self.user)


class ProfilMaitreStage(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_maitre_stage'
    )
    poste = models.CharField(max_length=150, blank=True)
    departement_affiliation = models.CharField(
        max_length=150, blank=True,
        help_text="Département d'appartenance du tuteur (informatif, distinct du département du stagiaire encadré)."
    )

    def __str__(self):
        return str(self.user)

    @property
    def nb_stagiaires_encadres(self):
        return self.stages_encadres.filter(statut=Stage.Statut.EN_COURS).count()

    @classmethod
    def creer_et_inviter(cls, nom_complet, email, poste='', departement_affiliation=''):
        """
        Crée un compte tuteur (sans mot de passe utilisable) et lui envoie un
        email d'activation à usage unique, sur le même principe que
        Candidature.accepter() pour les stagiaires. Tout est fait dans une
        seule transaction : en cas d'échec à n'importe quelle étape (compte
        déjà existant, erreur d'envoi d'e-mail...), rien n'est enregistré en
        base — pas de compte orphelin sans profil, ni de profil sans compte.
        """
        from django.db import transaction

        parties_nom = nom_complet.strip().split(' ', 1)
        base = ''.join(nom_complet.lower().split())

        with transaction.atomic():
            username, n = base, 1
            while User.objects.filter(username=username).exists():
                n += 1
                username = f"{base}{n}"

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=parties_nom[0],
                last_name=parties_nom[1] if len(parties_nom) > 1 else '',
                role=User.Role.MAITRE_STAGE,
            )
            user.set_unusable_password()
            user.save()

            # NB : la création de `user` ci-dessus déclenche le signal
            # `creer_profil_automatiquement` (signals.py), qui crée déjà un
            # ProfilMaitreStage vide pour ce user. On le récupère et on le
            # complète ici, plutôt que d'en créer un second (ce qui violait
            # la contrainte d'unicité sur `user` et provoquait un IntegrityError
            # à chaque création, quel que soit l'utilisateur).
            profil, _ = cls.objects.get_or_create(user=user)
            profil.poste = poste
            profil.departement_affiliation = departement_affiliation
            profil.save()

            from django.contrib.auth.tokens import default_token_generator
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            from django.urls import reverse
            from django.utils.encoding import force_bytes
            from django.utils.http import urlsafe_base64_encode

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            lien_relatif = reverse('appStage:activer_compte', kwargs={'uidb64': uidb64, 'token': token})
            lien_complet = f"{dj_settings.SITE_URL}{lien_relatif}"

            send_mail(
                subject="Votre compte tuteur - BCBStageFlow",
                message=(
                    f"Bonjour {nom_complet},\n\n"
                    f"Un compte tuteur de stage vient d'être créé pour vous sur BCBStageFlow.\n\n"
                    f"Pour y accéder, définissez votre mot de passe en suivant ce lien "
                    f"(valable 48 heures) :\n{lien_complet}\n\n"
                    f"L'équipe BCBStageFlow"
                ),
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

        return profil


class ProfilDirecteur(models.Model):
    """
    Directeur d'un service/département. Un directeur ne dirige qu'un
    seul département (relation directe Departement -> ProfilDirecteur,
    voir champ Departement.directeur).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_directeur'
    )
    poste = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return str(self.user)

    @property
    def departement_dirige(self):
        return getattr(self, 'departement', None)

    @classmethod
    def creer_et_inviter(cls, nom_complet, email, departement, poste=''):
        """
        Crée un compte directeur (sans mot de passe utilisable), le rattache
        au département fourni, et lui envoie un email d'activation à usage
        unique — même principe que ProfilMaitreStage.creer_et_inviter().
        """
        from django.db import transaction

        parties_nom = nom_complet.strip().split(' ', 1)
        base = ''.join(nom_complet.lower().split())

        with transaction.atomic():
            username, n = base, 1
            while User.objects.filter(username=username).exists():
                n += 1
                username = f"{base}{n}"

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=parties_nom[0],
                last_name=parties_nom[1] if len(parties_nom) > 1 else '',
                role=User.Role.DIRECTEUR,
            )
            user.set_unusable_password()
            user.save()

            # Le signal creer_profil_automatiquement a déjà créé un profil
            # vide pour ce user : on le récupère plutôt que d'en recréer un
            # second (contrainte d'unicité sur `user`).
            profil, _ = cls.objects.get_or_create(user=user)
            profil.poste = poste
            profil.save()

            departement.directeur = profil
            departement.save(update_fields=['directeur'])

            from django.contrib.auth.tokens import default_token_generator
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            from django.urls import reverse
            from django.utils.encoding import force_bytes
            from django.utils.http import urlsafe_base64_encode

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            lien_relatif = reverse('appStage:activer_compte', kwargs={'uidb64': uidb64, 'token': token})
            lien_complet = f"{dj_settings.SITE_URL}{lien_relatif}"

            send_mail(
                subject="Votre compte directeur - BCBStageFlow",
                message=(
                    f"Bonjour {nom_complet},\n\n"
                    f"Un compte directeur de service vient d'être créé pour vous sur BCBStageFlow, "
                    f"pour le département « {departement.nom} ».\n\n"
                    f"Pour y accéder, définissez votre mot de passe en suivant ce lien "
                    f"(valable 48 heures) :\n{lien_complet}\n\n"
                    f"L'équipe BCBStageFlow"
                ),
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

        return profil


# =========================================================
# Structure organisationnelle
# =========================================================

class Departement(models.Model):
    nom = models.CharField(max_length=150)
    agence = models.CharField(max_length=150, blank=True, help_text="Ville / agence de rattachement.")
    directeur = models.OneToOneField(
        ProfilDirecteur, on_delete=models.SET_NULL, null=True, blank=True, related_name='departement'
    )

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} • {self.agence}" if self.agence else self.nom


# =========================================================
# Recrutement
# =========================================================

class Candidature(models.Model):
    """
    Demande de stage soumise AVANT toute création de compte utilisateur.
    Le RH la traite (accepte ou refuse) ; c'est cette action qui,
    en cas d'acceptation, déclenche la création du User + ProfilStagiaire + Stage.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        ACCEPTEE = 'ACCEPTEE', 'Acceptée'
        REFUSEE = 'REFUSEE', 'Refusée'

    nom_complet = models.CharField(max_length=200)
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True, validators=[validateur_telephone_bf])
    poste_souhaite = models.CharField(max_length=200)
    filiere = models.CharField(max_length=150, blank=True, help_text="Transmise au profil du stagiaire si accepté.")
    annee_etude = models.CharField(
        max_length=20, choices=AnneeEtude.choices, blank=True,
        help_text="Année d'étude actuelle du candidat.",
    )
    cv = models.FileField(upload_to='candidatures/cv/', blank=True, null=True)
    lettre_motivation = models.FileField(upload_to='candidatures/lm/', blank=True, null=True)
    piece_identite = models.FileField(
        upload_to='candidatures/cnib/', blank=True, null=True,
        help_text="Copie de la CNIB (ou équivalent) du candidat.",
    )
    avec_soutenance_souhaite = models.BooleanField(
        default=True,
        help_text="Préférence exprimée par le candidat, que le RH confirme ou ajuste à l'acceptation.",
    )
    departement_souhaite = models.ForeignKey(
        Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidatures_souhaitees',
        help_text="Département choisi par le candidat, que le RH confirme ou ajuste à l'acceptation.",
    )

    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    motif_refus = models.TextField(blank=True, help_text="Obligatoire côté formulaire si la candidature est refusée.")

    departement_affecte = models.ForeignKey(
        Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidatures'
    )
    traite_par = models.ForeignKey(
        ProfilRH, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidatures_traitees'
    )
    stagiaire_cree = models.OneToOneField(
        ProfilStagiaire, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidature_origine'
    )

    date_soumission = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_soumission']

    def __str__(self):
        return f"{self.nom_complet} • {self.poste_souhaite}"

    def refuser(self, motif, traite_par):
        """Marque la candidature comme refusée avec justification obligatoire, et notifie le candidat par email."""
        if not motif:
            raise ValueError("Un motif de refus est obligatoire.")
        self.statut = self.Statut.REFUSEE
        self.motif_refus = motif
        self.traite_par = traite_par
        self.date_traitement = timezone.now()
        self.save()
        self._envoyer_email_refus()

    def accepter(self, departement, traite_par, date_debut, date_fin, avec_soutenance=True):
        """
        Accepte la candidature : crée le compte utilisateur (sans mot de
        passe utilisable), son profil, le Stage correspondant, puis envoie
        un email avec un lien d'activation à usage unique permettant au
        stagiaire de définir lui-même son mot de passe.
        """
        parties_nom = self.nom_complet.strip().split(' ', 1)
        user = User.objects.create_user(
            username=self._generer_username(),
            email=self.email,
            first_name=parties_nom[0],
            last_name=parties_nom[1] if len(parties_nom) > 1 else '',
            role=User.Role.STAGIAIRE,
        )
        user.set_unusable_password()
        user.save()

        profil = ProfilStagiaire.objects.create(
            user=user, filiere=self.filiere, annee_etude=self.annee_etude,
        )

        stage = Stage.objects.create(
            stagiaire=profil,
            departement=departement,
            intitule_poste=self.poste_souhaite,
            date_debut=date_debut,
            date_fin=date_fin,
            avec_soutenance=avec_soutenance,
            statut=Stage.Statut.A_VENIR,
        )

        self.statut = self.Statut.ACCEPTEE
        self.departement_affecte = departement
        self.traite_par = traite_par
        self.stagiaire_cree = profil
        self.date_traitement = timezone.now()
        self.save()

        lien_activation = self._envoyer_email_activation(user)
        stage.notifier_directeur_affectation()

        return user, stage, lien_activation

    def _envoyer_email_activation(self, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        lien_relatif = reverse('appStage:activer_compte', kwargs={'uidb64': uidb64, 'token': token})
        lien_complet = f"{dj_settings.SITE_URL}{lien_relatif}"

        send_mail(
            subject="Votre candidature a été acceptée - BCBStageFlow",
            message=(
                f"Bonjour {self.nom_complet},\n\n"
                f"Votre candidature au poste de {self.poste_souhaite} a été acceptée !\n\n"
                f"Pour accéder à votre tableau de bord, définissez votre mot de passe "
                f"en suivant ce lien (valable 48 heures) :\n{lien_complet}\n\n"
                f"L'équipe BCBStageFlow"
            ),
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
            fail_silently=False,
        )
        return lien_complet

    def _envoyer_email_refus(self):
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings

        send_mail(
            subject="Réponse à votre candidature - BCBStageFlow",
            message=(
                f"Bonjour {self.nom_complet},\n\n"
                f"Nous vous remercions pour votre candidature au poste de {self.poste_souhaite}.\n\n"
                f"Après étude de votre dossier, nous ne sommes malheureusement pas en mesure "
                f"d'y donner suite pour le motif suivant :\n\n{self.motif_refus}\n\n"
                f"Nous vous souhaitons plein succès dans vos démarches.\n\n"
                f"L'équipe BCBStageFlow"
            ),
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
            fail_silently=False,
        )

    def notifier_rh(self):
        """
        Prévient toute l'équipe RH par email dès qu'une nouvelle candidature
        arrive, pour qu'elle n'ait pas à surveiller la page en continu.
        N'empêche jamais la soumission de la candidature si l'envoi échoue
        (fail_silently) : le RH la verra de toute façon sur son dashboard.
        """
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse

        emails_rh = list(
            User.objects.filter(role=User.Role.RH, is_active=True)
            .exclude(email='').values_list('email', flat=True)
        )
        if not emails_rh:
            return

        lien_complet = f"{dj_settings.SITE_URL}{reverse('appStage:candidatures')}"
        send_mail(
            subject="Nouvelle candidature reçue - BCBStageFlow",
            message=(
                f"Une nouvelle candidature vient d'être déposée.\n\n"
                f"Candidat : {self.nom_complet}\n"
                f"Poste souhaité : {self.poste_souhaite}\n"
                f"Email : {self.email}\n"
                f"Téléphone : {self.telephone or 'non renseigné'}\n\n"
                f"Pour la consulter et y répondre :\n{lien_complet}"
            ),
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails_rh,
            fail_silently=True,
        )

    def _generer_username(self):
        base = ''.join(self.nom_complet.lower().split())
        username, n = base, 1
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base}{n}"
        return username


# =========================================================
# Cœur métier : le stage
# =========================================================

class Stage(models.Model):
    class Statut(models.TextChoices):
        A_VENIR = 'A_VENIR', 'À venir'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Terminé'
        RESILIE = 'RESILIE', 'Résilié'

    stagiaire = models.ForeignKey(
        ProfilStagiaire, on_delete=models.CASCADE, related_name='stages'
    )
    departement = models.ForeignKey(
        Departement, on_delete=models.PROTECT, related_name='stages'
    )
    maitre_de_stage = models.ForeignKey(
        ProfilMaitreStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stages_encadres'
    )
    intitule_poste = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_VENIR)

    # Un stage "sans soutenance" n'exige ni rapports, ni maître de stage,
    # ni évaluation formelle (cas des stages courts / d'observation).
    avec_soutenance = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date_debut']

    def __str__(self):
        return f"{self.stagiaire} • {self.intitule_poste}"

    @property
    def duree_totale_semaines(self):
        return max(1, round((self.date_fin - self.date_debut).days / 7))

    @property
    def semaines_ecoulees(self):
        aujourdhui = timezone.now().date()
        if aujourdhui < self.date_debut:
            return 0
        ecoulees = round((min(aujourdhui, self.date_fin) - self.date_debut).days / 7)
        return min(ecoulees, self.duree_totale_semaines)

    @property
    def semaines_restantes(self):
        return max(0, self.duree_totale_semaines - self.semaines_ecoulees)

    @property
    def progression_pourcentage(self):
        return round((self.semaines_ecoulees / self.duree_totale_semaines) * 100)

    @property
    def taux_presence(self):
        """
        À appeler seulement après synchroniser_presences(). Ne compte QUE les
        jours confirmés par le tuteur (valide_par_tuteur=True) : sans ça, un
        stagiaire pourrait afficher un taux flatteur simplement en pointant
        sans jamais se faire réellement valider — ce qui viderait de son
        sens tout le système de confirmation.
        """
        confirmees = self.presences.filter(valide_par_tuteur=True)
        total = confirmees.count()
        if not total:
            return None
        presents = confirmees.filter(present=True).count()
        return round((presents / total) * 100)

    def synchroniser_presences(self):
        """
        Crée une Presence 'absente' pour chaque jour ouvré déjà écoulé
        (jusqu'à hier — délai de grâce jusqu'à minuit pour pointer) sans
        aucun enregistrement. À appeler avant toute lecture de taux_presence
        ou de la liste des présences, pour que les jours ignorés comptent
        vraiment comme des absences plutôt que d'être simplement absents
        du calcul.
        """
        if self.statut not in (self.Statut.EN_COURS, self.Statut.TERMINE):
            return
        aujourdhui = timezone.now().date()
        dernier_jour = min(aujourdhui - datetime.timedelta(days=1), self.date_fin)
        if dernier_jour < self.date_debut:
            return
        jours_existants = set(self.presences.values_list('date', flat=True))
        a_creer = []
        jour = self.date_debut
        while jour <= dernier_jour:
            if jour.weekday() < 5 and jour not in jours_existants:  # jours ouvrés seulement
                a_creer.append(Presence(stage=self, date=jour, present=False, justifie=False))
            jour += datetime.timedelta(days=1)
        if a_creer:
            Presence.objects.bulk_create(a_creer, ignore_conflicts=True)

    @property
    def jours_restants(self):
        return (self.date_fin - timezone.now().date()).days

    @property
    def se_termine_bientot(self):
        """Encore en cours, mais à moins de 10 jours de la date de fin prévue."""
        return self.statut == self.Statut.EN_COURS and 0 <= self.jours_restants <= 10

    @property
    def periode_depassee(self):
        """Toujours marqué 'en cours' alors que la date de fin est passée : à clôturer."""
        return self.statut == self.Statut.EN_COURS and self.jours_restants < 0

    @property
    def demarre_bientot(self):
        """Pas encore commencé, mais à moins de 10 jours de la date de début prévue."""
        if self.statut != self.Statut.A_VENIR:
            return False
        return 0 <= self.jours_avant_debut <= 10

    @property
    def jours_avant_debut(self):
        return (self.date_debut - timezone.now().date()).days

    def notifier_directeur_affectation(self):
        """
        Prévient par email (et via une Notification in-app) le directeur du
        département auquel ce stagiaire vient d'être affecté par le RH, pour
        qu'il choisisse à son tour un maître de stage. N'empêche jamais
        l'affectation elle-même si l'envoi échoue (fail_silently).
        """
        directeur = getattr(self.departement, 'directeur', None)
        if not directeur or not directeur.user_id:
            return

        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse

        Notification.creer(
            destinataire=directeur.user,
            message=f"{self.stagiaire.user.get_full_name()} a été affecté(e) à votre service. "
                    f"Choisissez-lui un maître de stage.",
            lien=reverse('appStage:affecter_maitre_stage'),
        )

        lien_complet = f"{dj_settings.SITE_URL}{reverse('appStage:affecter_maitre_stage')}"
        send_mail(
            subject="Nouveau stagiaire affecté à votre service - BCBStageFlow",
            message=(
                f"Bonjour {directeur.user.get_full_name()},\n\n"
                f"{self.stagiaire.user.get_full_name()} vient d'être affecté(e) à votre service "
                f"({self.departement.nom}) pour le poste de {self.intitule_poste}.\n\n"
                f"Merci de lui choisir un maître de stage :\n{lien_complet}\n\n"
                f"L'équipe BCBStageFlow"
            ),
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[directeur.user.email],
            fail_silently=True,
        )

    @classmethod
    def synchroniser_statuts(cls):
        """
        Met à jour automatiquement le statut des stages en fonction de la date du jour :
        À venir -> En cours -> Terminé. Le statut « Résilié » reste manuel et n'est
        jamais touché ici. À appeler au début des vues qui affichent des stages,
        pour que le badge et les listes reflètent toujours la réalité des dates.
        """
        aujourdhui = timezone.now().date()
        cls.objects.exclude(statut=cls.Statut.RESILIE) \
            .filter(date_fin__lt=aujourdhui) \
            .exclude(statut=cls.Statut.TERMINE) \
            .update(statut=cls.Statut.TERMINE)
        cls.objects.exclude(statut=cls.Statut.RESILIE) \
            .filter(date_debut__lte=aujourdhui, date_fin__gte=aujourdhui) \
            .exclude(statut=cls.Statut.EN_COURS) \
            .update(statut=cls.Statut.EN_COURS)
        cls.objects.exclude(statut=cls.Statut.RESILIE) \
            .filter(date_debut__gt=aujourdhui) \
            .exclude(statut=cls.Statut.A_VENIR) \
            .update(statut=cls.Statut.A_VENIR)


class DemandeEncadrement(models.Model):
    """
    Classe-association entre Stage et ProfilMaitreStage : matérialise la
    proposition d'encadrement faite par le directeur du service à un tuteur
    potentiel, que celui-ci accepte ou refuse depuis son propre tableau de
    bord (l'affectation n'est effective qu'après acceptation du tuteur).
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        ACCEPTEE = 'ACCEPTEE', 'Acceptée'
        REFUSEE = 'REFUSEE', 'Refusée'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='demandes_encadrement')
    maitre_de_stage_demande = models.ForeignKey(
        ProfilMaitreStage, on_delete=models.CASCADE, related_name='demandes_recues'
    )
    proposee_par = models.ForeignKey(
        ProfilDirecteur, on_delete=models.SET_NULL, null=True, blank=True, related_name='propositions_encadrement',
        help_text="Directeur de service à l'origine de la proposition.",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    date_demande = models.DateTimeField(auto_now_add=True)
    date_reponse = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_demande']

    def __str__(self):
        return f"Demande {self.stage.stagiaire} → {self.maitre_de_stage_demande}"

    def notifier_tuteur(self):
        """Email + notification in-app envoyés au tuteur pressenti, dès la création de la demande."""
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse

        tuteur_user = self.maitre_de_stage_demande.user
        Notification.creer(
            destinataire=tuteur_user,
            message=f"On vous propose d'encadrer {self.stage.stagiaire.user.get_full_name()}.",
            lien=reverse('appStage:dashboard_tuteur'),
        )
        lien_complet = f"{dj_settings.SITE_URL}{reverse('appStage:dashboard_tuteur')}"
        send_mail(
            subject="Proposition d'encadrement - BCBStageFlow",
            message=(
                f"Bonjour {tuteur_user.get_full_name()},\n\n"
                f"Le directeur du service {self.stage.departement.nom} vous propose d'encadrer "
                f"{self.stage.stagiaire.user.get_full_name()} ({self.stage.intitule_poste}).\n\n"
                f"Pour accepter ou refuser :\n{lien_complet}\n\n"
                f"L'équipe BCBStageFlow"
            ),
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[tuteur_user.email],
            fail_silently=True,
        )

    def accepter(self):
        self.statut = self.Statut.ACCEPTEE
        self.date_reponse = timezone.now()
        self.save()
        self.stage.maitre_de_stage = self.maitre_de_stage_demande
        self.stage.save(update_fields=['maitre_de_stage'])
        self._notifier_reponse(acceptee=True)

    def refuser(self):
        self.statut = self.Statut.REFUSEE
        self.date_reponse = timezone.now()
        self.save()
        self._notifier_reponse(acceptee=False)

    def _notifier_reponse(self, acceptee):
        """Prévient le stagiaire et le directeur de la décision du tuteur."""
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings

        tuteur_nom = self.maitre_de_stage_demande.user.get_full_name()
        stagiaire_user = self.stage.stagiaire.user
        directeur = getattr(self.stage.departement, 'directeur', None)

        if acceptee:
            message_stagiaire = f"{tuteur_nom} est désormais votre maître de stage."
            message_directeur = f"{tuteur_nom} a accepté d'encadrer {stagiaire_user.get_full_name()}."
        else:
            message_stagiaire = f"{tuteur_nom} n'a pas pu accepter de vous encadrer. Votre directeur va vous proposer un autre tuteur."
            message_directeur = f"{tuteur_nom} a refusé d'encadrer {stagiaire_user.get_full_name()} : choisissez un autre tuteur."

        from django.urls import reverse

        Notification.creer(destinataire=stagiaire_user, message=message_stagiaire)
        if directeur and directeur.user_id:
            Notification.creer(
                destinataire=directeur.user, message=message_directeur,
                lien=reverse('appStage:affecter_maitre_stage'),
            )
            send_mail(
                subject="Réponse à une proposition d'encadrement - BCBStageFlow",
                message=f"Bonjour {directeur.user.get_full_name()},\n\n{message_directeur}\n\nL'équipe BCBStageFlow",
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[directeur.user.email],
                fail_silently=True,
            )

        if stagiaire_user.email:
            send_mail(
                subject="Votre encadrement de stage - BCBStageFlow",
                message=f"Bonjour {stagiaire_user.get_full_name()},\n\n{message_stagiaire}\n\nL'équipe BCBStageFlow",
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[stagiaire_user.email],
                fail_silently=True,
            )


class Entretien(models.Model):
    """Rencontre RH ↔ stagiaire, consignée par le RH et visible sur le dashboard du stagiaire."""

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='entretiens')
    rh = models.ForeignKey(ProfilRH, on_delete=models.SET_NULL, null=True, related_name='entretiens_menes')
    date = models.DateTimeField(default=timezone.now)
    compte_rendu = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Entretien {self.date:%d/%m/%Y} • {self.stage}"


class Evaluation(models.Model):
    class TypeEvaluation(models.TextChoices):
        MI_PARCOURS = 'MI_PARCOURS', 'Mi-parcours'
        FINALE = 'FINALE', 'Finale'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='evaluations')
    type_evaluation = models.CharField(max_length=20, choices=TypeEvaluation.choices)

    # Notation par critère (sur 20 chacun) : la note globale est leur moyenne,
    # affichée en anneau de progression sur le formulaire d'évaluation.
    note_technique = models.PositiveSmallIntegerField(default=10)
    note_autonomie = models.PositiveSmallIntegerField(default=10)
    note_communication = models.PositiveSmallIntegerField(default=10)
    note_ponctualite = models.PositiveSmallIntegerField(default=10)

    commentaire = models.TextField(blank=True)
    date_evaluation = models.DateField(auto_now_add=True)

    class Meta:
        # date_evaluation n'a qu'une précision journalière : sans le tri
        # secondaire sur id, deux évaluations créées le même jour peuvent
        # apparaître dans un ordre non garanti — et donc afficher la
        # mauvaise comme "dernière évaluation" au stagiaire.
        ordering = ['-date_evaluation', '-id']

    def __str__(self):
        return f"Évaluation {self.get_type_evaluation_display()} • {self.stage}"

    @property
    def note(self):
        """Note globale sur 20, moyenne des 4 critères."""
        return round((self.note_technique + self.note_autonomie
                      + self.note_communication + self.note_ponctualite) / 4, 1)


class Mission(models.Model):
    class Statut(models.TextChoices):
        A_FAIRE = 'A_FAIRE', 'À faire'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINEE = 'TERMINEE', 'Terminée'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='missions')
    titre = models.CharField(max_length=200)
    equipe = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    echeance = models.DateField(null=True, blank=True)
    fichier = models.FileField(
        upload_to='missions/', blank=True, null=True,
        help_text="Document de support ou consigne détaillée (optionnel).",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_FAIRE)

    class Meta:
        ordering = ['echeance']

    def __str__(self):
        return self.titre

    def notifier_stagiaire(self):
        """Email + notification in-app au stagiaire dès qu'une mission lui est assignée."""
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse

        stagiaire_user = self.stage.stagiaire.user
        lien_relatif = reverse('appStage:mes_missions')
        Notification.creer(
            destinataire=stagiaire_user,
            message=f"Nouvelle mission assignée : « {self.titre} ».",
            lien=lien_relatif,
        )
        if stagiaire_user.email:
            send_mail(
                subject="Nouvelle mission assignée - BCBStageFlow",
                message=(
                    f"Bonjour {stagiaire_user.get_full_name()},\n\n"
                    f"Une nouvelle mission vous a été assignée : « {self.titre} ».\n\n"
                    f"{('Description : ' + self.description) if self.description else ''}\n\n"
                    f"Consultez-la ici :\n{dj_settings.SITE_URL}{lien_relatif}\n\n"
                    f"L'équipe BCBStageFlow"
                ),
                from_email=dj_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[stagiaire_user.email],
                fail_silently=True,
            )


class RapportHebdomadaire(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        VALIDE = 'VALIDE', 'Validé'
        EN_RETARD = 'EN_RETARD', 'En retard'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='rapports')
    numero_semaine = models.PositiveIntegerField()
    contenu = models.TextField(blank=True)
    fichier = models.FileField(upload_to='rapports/', blank=True, null=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    date_soumission = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-numero_semaine']

    def __str__(self):
        return f"Rapport S{self.numero_semaine} • {self.stage}"

    def valider(self):
        self.statut = self.Statut.VALIDE
        self.save(update_fields=['statut'])


class Presence(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='presences')
    date = models.DateField()
    present = models.BooleanField(default=True)
    justifie = models.BooleanField(default=False)
    note_activite = models.CharField(
        max_length=280, blank=True,
        help_text="Courte description de ce qui a été fait ce jour-là, saisie par le stagiaire au moment de pointer.",
    )
    valide_par_tuteur = models.BooleanField(
        default=False, help_text="Auto-déclarée par le stagiaire, puis confirmée par le maître de stage."
    )

    class Meta:
        unique_together = ('stage', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.stage} • {self.date}"

    def valider(self):
        self.valide_par_tuteur = True
        self.save(update_fields=['valide_par_tuteur'])


class DocumentStage(models.Model):
    """
    Document administratif ou de suivi rattaché au stage. Regroupe ce qui
    était auparavant une classe Convention séparée : une convention de
    stage est simplement un DocumentStage avec type_document='CONVENTION'.
    Le statut de signature (statut/date_signature) n'a de sens que pour
    les types CONVENTION et CONTRAT.
    """

    class TypeDocument(models.TextChoices):
        CONVENTION = 'CONVENTION', 'Accord de stage'
        CONTRAT = 'CONTRAT', 'Contrat'
        RAPPORT = 'RAPPORT', 'Rapport'
        AUTRE = 'AUTRE', 'Autre'

    class StatutSignature(models.TextChoices):
        NON_APPLICABLE = 'NON_APPLICABLE', 'Non applicable'
        EN_ATTENTE = 'EN_ATTENTE', 'En attente de signature'
        SIGNE = 'SIGNE', 'Signé'

    class Destinataire(models.TextChoices):
        TUTEUR = 'TUTEUR', 'Maître de stage'
        RH = 'RH', 'RH'
        STAGIAIRE = 'STAGIAIRE', 'Stagiaire'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='documents')
    mission = models.ForeignKey(
        'Mission', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents',
        help_text="Mission à laquelle ce document se rapporte (livrable), le cas échéant.",
    )
    nom = models.CharField(max_length=200)
    fichier = models.FileField(upload_to='documents_stage/', blank=True, null=True)
    type_document = models.CharField(max_length=15, choices=TypeDocument.choices, default=TypeDocument.AUTRE)
    destinataire = models.CharField(
        max_length=15, choices=Destinataire.choices, default=Destinataire.TUTEUR,
        help_text="Qui doit voir/traiter ce document : le maître de stage, le RH, ou (documents émis "
                   "par le RH, ex. contrat) le stagiaire lui-même.",
    )
    statut_signature = models.CharField(
        max_length=20, choices=StatutSignature.choices, default=StatutSignature.NON_APPLICABLE
    )
    date_signature = models.DateField(null=True, blank=True)
    ajoute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_ajout']

    def __str__(self):
        return self.nom

    def notifier_depot_stagiaire(self):
        """
        Prévient par email (et via une Notification in-app) le directeur du
        service et, s'il est déjà assigné, le maître de stage, dès qu'un
        stagiaire dépose un document (ex. rapport de stage). N'empêche
        jamais le dépôt si l'envoi échoue (fail_silently).
        """
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        from django.urls import reverse

        stage = self.stage
        lien_relatif = reverse('appStage:fiche_stagiaire', kwargs={'stage_id': stage.id}) + '#documents'
        lien_complet = f"{dj_settings.SITE_URL}{lien_relatif}"
        stagiaire_nom = stage.stagiaire.user.get_full_name()

        destinataires_users = []
        directeur = getattr(stage.departement, 'directeur', None)
        if directeur and directeur.user_id:
            destinataires_users.append(directeur.user)
        if stage.maitre_de_stage_id and stage.maitre_de_stage.user_id:
            destinataires_users.append(stage.maitre_de_stage.user)

        for destinataire_user in destinataires_users:
            Notification.creer(
                destinataire=destinataire_user,
                message=f"{stagiaire_nom} a déposé un document : « {self.nom} ».",
                lien=lien_relatif,
            )
            if destinataire_user.email:
                send_mail(
                    subject="Nouveau document déposé - BCBStageFlow",
                    message=(
                        f"Bonjour {destinataire_user.get_full_name()},\n\n"
                        f"{stagiaire_nom} vient de déposer un document : « {self.nom} ».\n\n"
                        f"Pour le consulter :\n{lien_complet}\n\n"
                        f"L'équipe BCBStageFlow"
                    ),
                    from_email=dj_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[destinataire_user.email],
                    fail_silently=True,
                )


class Notification(models.Model):
    """
    Notification in-app minimale, affichée dans la cloche du tableau de
    bord. Vient en complément des emails (canal principal) envoyés par les
    méthodes métier ci-dessus — jamais en remplacement.
    """

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True, help_text="Chemin relatif vers lequel rediriger au clic.")
    lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.destinataire} • {self.message[:40]}"

    @classmethod
    def creer(cls, destinataire, message, lien=''):
        return cls.objects.create(destinataire=destinataire, message=message, lien=lien)
