from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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
        }.get(self.role, 'appStage:onboarding')


class ProfilStagiaire(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_stagiaire'
    )
    filiere = models.CharField(max_length=150, blank=True)
    annee_etude = models.CharField(max_length=50, blank=True)  # ex: "3ème Année"
    etablissement = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return str(self.user)

    @property
    def stage_actif(self):
        """Le stage en cours de ce stagiaire, s'il y en a un."""
        return self.stages.filter(statut=Stage.Statut.EN_COURS).first()


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


# =========================================================
# Structure organisationnelle
# =========================================================

class Departement(models.Model):
    nom = models.CharField(max_length=150)
    agence = models.CharField(max_length=150, blank=True, help_text="Ville / agence de rattachement.")

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} — {self.agence}" if self.agence else self.nom


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
    telephone = models.CharField(max_length=20, blank=True)
    poste_souhaite = models.CharField(max_length=200)
    cv = models.FileField(upload_to='candidatures/cv/', blank=True, null=True)
    lettre_motivation = models.FileField(upload_to='candidatures/lm/', blank=True, null=True)

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
        return f"{self.nom_complet} — {self.poste_souhaite}"

    def refuser(self, motif, traite_par):
        """Marque la candidature comme refusée avec justification obligatoire."""
        if not motif:
            raise ValueError("Un motif de refus est obligatoire.")
        self.statut = self.Statut.REFUSEE
        self.motif_refus = motif
        self.traite_par = traite_par
        self.date_traitement = timezone.now()
        self.save()

    def accepter(self, departement, traite_par, date_debut, date_fin, avec_soutenance=True):
        """
        Accepte la candidature : crée le compte utilisateur, son profil,
        et le Stage correspondant. Retourne le User créé (le mot de passe
        est laissé inutilisable ici — l'envoi du lien d'activation par
        email est géré côté vue, hors modèle).
        """
        user = User.objects.create_user(
            username=self._generer_username(),
            email=self.email,
            first_name=self.nom_complet.split(' ')[0],
            last_name=' '.join(self.nom_complet.split(' ')[1:]) or self.nom_complet,
            role=User.Role.STAGIAIRE,
        )
        user.set_unusable_password()
        user.save()

        profil = ProfilStagiaire.objects.create(user=user)

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

        return user, stage

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
        return f"{self.stagiaire} — {self.intitule_poste}"

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
        total = self.presences.count()
        if not total:
            return None
        presents = self.presences.filter(present=True).count()
        return round((presents / total) * 100)


class DemandeEncadrement(models.Model):
    """
    Classe-association entre Stage et ProfilMaitreStage : matérialise
    la demande du stagiaire à un tuteur potentiel, que celui-ci accepte
    ou refuse depuis son propre tableau de bord.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        ACCEPTEE = 'ACCEPTEE', 'Acceptée'
        REFUSEE = 'REFUSEE', 'Refusée'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='demandes_encadrement')
    maitre_de_stage_demande = models.ForeignKey(
        ProfilMaitreStage, on_delete=models.CASCADE, related_name='demandes_recues'
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    date_demande = models.DateTimeField(auto_now_add=True)
    date_reponse = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_demande']

    def __str__(self):
        return f"Demande {self.stage.stagiaire} → {self.maitre_de_stage_demande}"

    def accepter(self):
        self.statut = self.Statut.ACCEPTEE
        self.date_reponse = timezone.now()
        self.save()
        self.stage.maitre_de_stage = self.maitre_de_stage_demande
        self.stage.save(update_fields=['maitre_de_stage'])

    def refuser(self):
        self.statut = self.Statut.REFUSEE
        self.date_reponse = timezone.now()
        self.save()


class Entretien(models.Model):
    """Rencontre RH ↔ stagiaire, consignée par le RH et visible sur le dashboard du stagiaire."""

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='entretiens')
    rh = models.ForeignKey(ProfilRH, on_delete=models.SET_NULL, null=True, related_name='entretiens_menes')
    date = models.DateTimeField(default=timezone.now)
    compte_rendu = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Entretien {self.date:%d/%m/%Y} — {self.stage}"


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
        ordering = ['-date_evaluation']

    def __str__(self):
        return f"Évaluation {self.get_type_evaluation_display()} — {self.stage}"

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
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_FAIRE)

    class Meta:
        ordering = ['echeance']

    def __str__(self):
        return self.titre


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
        return f"Rapport S{self.numero_semaine} — {self.stage}"

    def valider(self):
        self.statut = self.Statut.VALIDE
        self.save(update_fields=['statut'])


class Presence(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='presences')
    date = models.DateField()
    present = models.BooleanField(default=True)
    justifie = models.BooleanField(default=False)
    valide_par_tuteur = models.BooleanField(
        default=False, help_text="Auto-déclarée par le stagiaire, puis confirmée par le maître de stage."
    )

    class Meta:
        unique_together = ('stage', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.stage} — {self.date}"

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
        CONVENTION = 'CONVENTION', 'Convention de stage'
        CONTRAT = 'CONTRAT', 'Contrat'
        RAPPORT = 'RAPPORT', 'Rapport'
        AUTRE = 'AUTRE', 'Autre'

    class StatutSignature(models.TextChoices):
        NON_APPLICABLE = 'NON_APPLICABLE', 'Non applicable'
        EN_ATTENTE = 'EN_ATTENTE', 'En attente de signature'
        SIGNE = 'SIGNE', 'Signé'

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='documents')
    nom = models.CharField(max_length=200)
    fichier = models.FileField(upload_to='documents_stage/', blank=True, null=True)
    type_document = models.CharField(max_length=15, choices=TypeDocument.choices, default=TypeDocument.AUTRE)
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
