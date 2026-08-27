from django import forms
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm

from .models import Candidature, Departement, DocumentStage, Evaluation, Mission, User


class CandidaturePubliqueForm(forms.ModelForm):
    """
    Formulaire public de dépôt de candidature — remplace l'ancienne
    inscription libre. Aucun compte n'est créé ici : seul le RH, en
    acceptant la candidature, déclenche la création du compte stagiaire.
    """

    class Meta:
        model = Candidature
        fields = [
            'nom_complet', 'email', 'telephone', 'poste_souhaite', 'departement_souhaite',
            'cv', 'lettre_motivation', 'piece_identite', 'avec_soutenance_souhaite',
        ]
        labels = {
            'nom_complet': "Nom complet",
            'email': "Adresse e-mail",
            'telephone': "Téléphone",
            'poste_souhaite': "Poste souhaité",
            'departement_souhaite': "Département souhaité",
            'cv': "CV",
            'lettre_motivation': "Lettre de motivation",
            'piece_identite': "Copie de la CNIB",
            'avec_soutenance_souhaite': "Ce stage donnera lieu à une soutenance / un rapport de fin de stage",
        }
        widgets = {
            'departement_souhaite': forms.Select(attrs={'required': False}),
        }


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
    par le RH, pas par le stagiaire lui-même.
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
        self.fields['mission'].empty_label = "Aucune — document indépendant"
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
