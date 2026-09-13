from django import forms
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.forms import SetPasswordForm

from .models import Candidature, Departement, DocumentStage, Evaluation, Mission, ProfilMaitreStage, User


class ActiverCompteForm(SetPasswordForm):
    """
    Étend le SetPasswordForm standard de Django avec un champ nom
    d'utilisateur choisi par la personne elle-même — sans ça, elle doit
    deviner le nom auto-généré à partir de son nom complet pour se
    reconnecter ensuite (ex. « borisouedraogo », pas « Boris » ni « Boris
    Ouedraogo »), ce qui n'est pas intuitif.
    """
    username = forms.CharField(
        label="Nom d'utilisateur",
        max_length=150,
        help_text="C'est ce nom (pas votre nom complet) qui vous servira à vous connecter.",
    )

    field_order = ['username', 'new_password1', 'new_password2']

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['username'].initial = user.username

    def clean_username(self):
        valeur = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=valeur).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris, choisissez-en un autre.")
        return valeur

    def save(self, commit=True):
        self.user.username = self.cleaned_data['username']
        return super().save(commit=commit)


class CandidaturePubliqueForm(forms.ModelForm):
    """
    Formulaire public de dépôt de candidature, remplace l'ancienne
    inscription libre. Aucun compte n'est créé ici : seul le RH, en
    acceptant la candidature, déclenche la création du compte stagiaire.
    """

    class Meta:
        model = Candidature
        fields = [
            'nom_complet', 'email', 'telephone', 'poste_souhaite',
            'filiere', 'annee_etude', 'departement_souhaite',
            'cv', 'lettre_motivation', 'piece_identite', 'avec_soutenance_souhaite',
        ]
        labels = {
            'nom_complet': "Nom complet",
            'email': "Adresse e-mail",
            'telephone': "Téléphone",
            'poste_souhaite': "Poste souhaité",
            'filiere': "Filière",
            'annee_etude': "Année d'étude actuelle",
            'departement_souhaite': "Département souhaité",
            'cv': "CV",
            'lettre_motivation': "Lettre de motivation",
            'piece_identite': "Copie de la CNIB",
            'avec_soutenance_souhaite': "Ce stage donnera lieu à une soutenance / un rapport de fin de stage",
        }
        widgets = {
            'departement_souhaite': forms.Select(attrs={'required': False}),
            'telephone': forms.TextInput(attrs={
                'placeholder': "70000000",
                'inputmode': 'numeric',
                'maxlength': '8',
                'pattern': r'[0-9]{8}',
                'title': "8 chiffres, sans le +226",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Documents obligatoires à la candidature (le formulaire ne le
        # précise pas nativement puisque ces champs sont optionnels côté
        # modèle — un stagiaire peut très bien ne jamais avoir eu besoin
        # de déposer de CV après son embauche, par exemple).
        self.fields['cv'].required = True
        self.fields['lettre_motivation'].required = True
        self.fields['piece_identite'].required = True

    def clean_telephone(self):
        brut = self.cleaned_data.get('telephone', '')
        chiffres = ''.join(c for c in brut if c.isdigit())
        # Tolère qu'on ait quand même tapé l'indicatif (+226 ou 00226) par réflexe.
        if chiffres.startswith('226') and len(chiffres) == 11:
            chiffres = chiffres[3:]
        if len(chiffres) != 8:
            raise forms.ValidationError(
                "Le numéro doit contenir exactement 8 chiffres (numéro burkinabè, sans l'indicatif)."
            )
        return f"+226{chiffres}"

    def clean_email(self):
        email = self.cleaned_data['email']
        deja_en_cours = Candidature.objects.filter(
            email__iexact=email,
            statut__in=[Candidature.Statut.EN_ATTENTE, Candidature.Statut.ACCEPTEE],
        ).exists()
        if deja_en_cours:
            raise forms.ValidationError(
                "Une candidature est déjà en cours avec cette adresse e-mail. "
                "Inutile de la soumettre à nouveau : notre équipe RH la traitera prochainement."
            )
        return email


class EvaluationForm(forms.ModelForm):
    """Notation par critère (sur 20 chacun) + commentaire — voir Evaluation.note (moyenne calculée)."""

    class Meta:
        model = Evaluation
        fields = [
            'type_evaluation', 'note_technique', 'note_autonomie',
            'note_communication', 'note_ponctualite', 'commentaire',
        ]
        widgets = {
            'note_technique': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_autonomie': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_communication': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_ponctualite': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'commentaire': forms.Textarea(attrs={'rows': 5, 'maxlength': 1000, 'placeholder': "Décrivez la performance, les points forts, les axes d'amélioration…"}),
        }
        labels = {
            'type_evaluation': "Type d'évaluation",
            'note_technique': "Compétences techniques",
            'note_autonomie': "Autonomie",
            'note_communication': "Communication",
            'note_ponctualite': "Ponctualité / Rigueur",
            'commentaire': "Commentaires détaillés",
        }


class AccepterCandidatureForm(forms.Form):
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.all(), label="Département d'affectation",
        empty_label="Choisir un département…",
    )
    date_debut = forms.DateField(label="Date de début", widget=forms.DateInput(attrs={'type': 'date'}))
    date_fin = forms.DateField(label="Date de fin", widget=forms.DateInput(attrs={'type': 'date'}))
    avec_soutenance = forms.BooleanField(
        label="Stage avec soutenance / rapports / tuteur", required=False, initial=True,
    )

    def clean(self):
        cleaned = super().clean()
        debut, fin = cleaned.get('date_debut'), cleaned.get('date_fin')
        if debut and fin and fin <= debut:
            raise forms.ValidationError("La date de fin doit être postérieure à la date de début.")
        return cleaned


class RefuserCandidatureForm(forms.Form):
    motif = forms.CharField(
        label="Motif du refus", widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )


class ParametresForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone', 'photo']
        labels = {
            'first_name': "Prénom",
            'last_name': "Nom",
            'email': "Adresse e-mail",
            'telephone': "Téléphone",
            'photo': "Photo de profil",
        }


class ChangerMotDePasseForm(DjangoPasswordChangeForm):
    """Wrapper simple autour du formulaire natif Django, pour l'onglet Sécurité des Paramètres."""
    pass


class AssignerMissionForm(forms.ModelForm):
    """Le champ `stage` est restreint (dans la vue) aux stagiaires réellement encadrés par le tuteur connecté."""

    class Meta:
        model = Mission
        fields = ['stage', 'titre', 'equipe', 'echeance', 'fichier', 'description']
        labels = {
            'stage': "Assigner à",
            'titre': "Titre de la mission",
            'equipe': "Équipe / Projet",
            'echeance': "Date d'échéance",
            'fichier': "Document de support (optionnel)",
            'description': "Description",
        }
        widgets = {
            'echeance': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': "Décrivez la mission, les objectifs attendus…"}),
        }


class SoumettreDocumentForm(forms.ModelForm):
    """
    Le stagiaire ne peut soumettre que des documents de type RAPPORT ou
    AUTRE — CONVENTION/CONTRAT restent des documents administratifs émis
    par le RH, pas par le stagiaire lui-même. Il ne choisit plus de
    destinataire : il dépose simplement son fichier, qui devient visible
    par le directeur de son service et son maître de stage (tous deux
    notifiés par email), sans passer par le RH.
    """

    class Meta:
        model = DocumentStage
        fields = ['nom', 'type_document', 'mission', 'fichier']
        labels = {
            'nom': "Nom du document",
            'type_document': "Type",
            'mission': "Mission concernée",
            'fichier': "Fichier",
        }

    def __init__(self, *args, stage=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type_document'].choices = [
            (val, label) for val, label in DocumentStage.TypeDocument.choices
            if val in (DocumentStage.TypeDocument.RAPPORT, DocumentStage.TypeDocument.AUTRE)
        ]
        self.fields['mission'].required = False
        self.fields['mission'].empty_label = "Aucune (document indépendant)"
        if stage is not None:
            queryset = stage.missions.exclude(statut=Mission.Statut.TERMINEE)
            if self.instance and self.instance.pk and self.instance.mission_id:
                # Garde la mission déjà liée même si elle est maintenant terminée,
                # sinon modifier un document dont la mission vient d'être complétée
                # ferait échouer la validation (mission absente du queryset).
                queryset = queryset | stage.missions.filter(pk=self.instance.mission_id)
            self.fields['mission'].queryset = queryset
        elif self.instance and self.instance.pk:
            self.fields['mission'].queryset = self.instance.stage.missions.all()
        else:
            self.fields['mission'].queryset = Mission.objects.none()


class EnvoyerDocumentRHForm(forms.ModelForm):
    """Le RH envoie un document administratif (convention, contrat, autre) à un stagiaire donné."""

    class Meta:
        model = DocumentStage
        fields = ['nom', 'type_document', 'fichier']
        labels = {
            'nom': "Nom du document",
            'type_document': "Type",
            'fichier': "Fichier",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type_document'].choices = [
            (val, label) for val, label in DocumentStage.TypeDocument.choices
            if val in (
                DocumentStage.TypeDocument.CONVENTION,
                DocumentStage.TypeDocument.CONTRAT,
                DocumentStage.TypeDocument.AUTRE,
            )
        ]
        self.fields['fichier'].required = True


class CreerTuteurForm(forms.Form):
    """Formulaire RH de création d'un compte tuteur (maître de stage)."""
    nom_complet = forms.CharField(label="Nom complet", max_length=200)
    email = forms.EmailField(label="Adresse e-mail")
    poste = forms.CharField(label="Poste", max_length=150, required=False)
    departement_affiliation = forms.CharField(label="Département d'appartenance", max_length=150, required=False)

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email


class CreerDirecteurForm(forms.Form):
    """Formulaire RH de création d'un compte directeur de service, rattaché à un département."""
    nom_complet = forms.CharField(label="Nom complet", max_length=200)
    email = forms.EmailField(label="Adresse e-mail")
    poste = forms.CharField(label="Poste", max_length=150, required=False)
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.filter(directeur__isnull=True),
        label="Département dirigé",
        empty_label="Choisir un département…",
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email


class CreerDepartementForm(forms.Form):
    """Formulaire RH de création d'un service/département."""
    nom = forms.CharField(label="Nom du service", max_length=150)
    agence = forms.CharField(label="Ville / agence", max_length=150, required=False)

    def clean_nom(self):
        nom = self.cleaned_data['nom'].strip()
        if Departement.objects.filter(nom__iexact=nom).exists():
            raise forms.ValidationError("Un service porte déjà ce nom.")
        return nom


class AffecterMaitreStageForm(forms.Form):
    """Le directeur propose un maître de stage pour un stagiaire de son service."""
    stage_id = forms.IntegerField(widget=forms.HiddenInput)
    tuteur = forms.ModelChoiceField(
        queryset=ProfilMaitreStage.objects.select_related('user'),
        label="Maître de stage proposé", empty_label="Choisir un tuteur…",
    )


class AffecterServiceForm(forms.Form):
    """Le RH affecte (ou réaffecte) un stagiaire à un département/service."""
    stage_id = forms.IntegerField(widget=forms.HiddenInput)
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.all(),
        label="Service", empty_label="Choisir un service…",
    )

